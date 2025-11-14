import shutil
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from uuid import uuid4

import click
from celery.result import AsyncResult
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from recollect_api.agent import GroqAgent
from recollect_api.celery_app import celery_app
from recollect_api.config import get_settings
from recollect_api.models import (
    AssistantMessageResponse,
    DownloadVideoRequest,
    DownloadVideoResponse,
    ProcessVideoRequest,
    ProcessVideoResponse,
    ResetMemoryResponse,
    UserMessageRequest,
    VideoUploadResponse,
)
from recollect_api.tasks import download_video_task, process_video_task

settings = get_settings()


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_FOUND = "not_found"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = GroqAgent(
        name="recollect",
        mcp_server=settings.MCP_SERVER,
        disable_tools=["process_video"],
    )
    yield
    app.state.agent.reset_memory()


app = FastAPI(
    title="Recollect API",
    description="An AI-powered sports assistant API using OpenAI",
    docs_url="/docs",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for media serving
app.mount("/media", StaticFiles(directory="shared_media"), name="media")


@app.get("/")
async def root():
    """
    Root endpoint that redirects to API documentation
    """
    return {"message": "Welcome to Recollect API. Visit /docs for documentation"}


@app.get("/health")
async def health_check():
    """
    Health check endpoint for container health monitoring
    """
    return {"status": "healthy", "service": "recollect-api"}


@app.get("/ready")
async def readiness_check(request: Request):
    """
    Readiness check endpoint - verifies all dependencies are available
    """
    try:
        # Check if agent is initialized
        if not hasattr(request.app.state, "agent"):
            return {"status": "not_ready", "reason": "agent_not_initialized"}, 503

        return {"status": "ready", "service": "recollect-api"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "not_ready", "reason": str(e)}, 503


@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    Get the status of a Celery task
    """
    try:
        task_result = AsyncResult(task_id, app=celery_app)

        if task_result.state == "PENDING":
            status = TaskStatus.PENDING
        elif task_result.state == "PROCESSING":
            status = TaskStatus.IN_PROGRESS
        elif task_result.state == "SUCCESS":
            status = TaskStatus.COMPLETED
        elif task_result.state == "FAILURE":
            status = TaskStatus.FAILED
        else:
            status = task_result.state

        response = {
            "task_id": task_id,
            "status": status,
            "state": task_result.state,
        }

        if task_result.info:
            response["info"] = task_result.info

        return response
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        return {"task_id": task_id, "status": TaskStatus.NOT_FOUND}


@app.post("/process-video")
async def process_video(request: ProcessVideoRequest):
    """
    Process a video using Celery task queue
    """
    if not Path(request.video_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    try:
        # Dispatch Celery task
        task = process_video_task.delay(request.video_path)
        logger.info(f"Dispatched video processing task: {task.id} for {request.video_path}")

        return ProcessVideoResponse(
            message="Video processing task enqueued",
            task_id=task.id
        )
    except Exception as e:
        logger.error(f"Error dispatching video processing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=AssistantMessageResponse)
async def chat(request: UserMessageRequest, fastapi_request: Request):
    """
    Chat with the AI assistant

    Args:
        request: ChatRequest containing the message and optional image URL

    Returns:
        ChatResponse containing the assistant's response
    """
    agent = fastapi_request.app.state.agent
    await agent.setup()

    try:
        response = await agent.chat(request.message, request.video_path, request.image_base64)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset-memory")
async def reset_memory(fastapi_request: Request):
    """
    Reset the memory of the agent
    """
    agent = fastapi_request.app.state.agent
    agent.reset_memory()
    return ResetMemoryResponse(message="Memory reset successfully")


@app.post("/upload-video", response_model=VideoUploadResponse)
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a video and return the path
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        shared_media_dir = Path("shared_media")
        shared_media_dir.mkdir(exist_ok=True)

        video_path = Path(shared_media_dir / file.filename)
        if not video_path.exists():
            with open(video_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

        return VideoUploadResponse(message="Video uploaded successfully", video_path=str(video_path))
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/download-video", response_model=DownloadVideoResponse)
async def download_video(request: DownloadVideoRequest):
    """
    Download content from Instagram, YouTube, LinkedIn, or TikTok URL using Celery task queue

    Supported platforms:
    - Instagram: Reels and regular posts
    - YouTube: Videos and Shorts
    - LinkedIn: Video posts, image posts, and carousels
    - TikTok: Video posts

    Returns a task_id for tracking the download progress.
    """
    try:
        # Dispatch Celery task
        task = download_video_task.delay(request.url)
        logger.info(f"Dispatched video download task: {task.id} for {request.url}")

        return DownloadVideoResponse(
            message="Video download task enqueued",
            task_id=task.id
        )
    except Exception as e:
        logger.error(f"Error dispatching video download task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/media/{file_path:path}")
async def serve_media(file_path: str):
    """
    Serve media files from the shared_media directory
    """
    try:
        clean_path = Path(file_path).name
        media_file = Path("shared_media") / clean_path

        if not media_file.exists():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(str(media_file))
    except Exception as e:
        logger.error(f"Error serving media file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@click.command()
@click.option("--port", default=8080, help="FastAPI server port")
@click.option("--host", default="0.0.0.0", help="FastAPI server host")
def run_api(port, host):
    import uvicorn

    uvicorn.run("api:app", host=host, port=port, loop="asyncio")


if __name__ == "__main__":
    run_api()
