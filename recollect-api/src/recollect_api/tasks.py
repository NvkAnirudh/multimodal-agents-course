"""Celery tasks for async processing"""
from pathlib import Path
from loguru import logger
from fastmcp.client import Client
from recollect_api.celery_app import celery_app
from recollect_api.config import get_settings

settings = get_settings()


@celery_app.task(bind=True, name="recollect.process_video")
def process_video_task(self, video_path: str) -> dict:
    """
    Process a video file asynchronously

    Args:
        video_path: Path to the video file

    Returns:
        dict: Processing result with status and metadata
    """
    logger.info(f"Starting video processing task for: {video_path}")

    if not Path(video_path).exists():
        logger.error(f"Video file not found: {video_path}")
        return {
            "status": "failed",
            "error": "Video file not found",
            "video_path": video_path,
        }

    try:
        # Update task state
        self.update_state(
            state="PROCESSING",
            meta={
                "video_path": video_path,
                "status": "processing",
            }
        )

        # Process video using MCP server
        mcp_client = Client(settings.MCP_SERVER)
        result = mcp_client.call_tool_sync("process_video", {"video_path": video_path})

        logger.info(f"Video processing completed for: {video_path}")
        return {
            "status": "completed",
            "video_path": video_path,
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error processing video {video_path}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "video_path": video_path,
        }


@celery_app.task(bind=True, name="recollect.download_video")
def download_video_task(self, url: str, source: str) -> dict:
    """
    Download a video from Instagram or YouTube

    Args:
        url: Video URL
        source: Video source ('instagram' or 'youtube')

    Returns:
        dict: Download result with status and file path
    """
    logger.info(f"Starting video download task for: {url} (source: {source})")

    try:
        # Update task state
        self.update_state(
            state="DOWNLOADING",
            meta={
                "url": url,
                "source": source,
                "status": "downloading",
            }
        )

        # TODO: Implement video download logic
        # This will be implemented in the next task

        logger.info(f"Video download completed for: {url}")
        return {
            "status": "completed",
            "url": url,
            "source": source,
            "file_path": "placeholder",
        }

    except Exception as e:
        logger.error(f"Error downloading video {url}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "url": url,
            "source": source,
        }
