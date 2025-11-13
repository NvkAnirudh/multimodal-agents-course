# Recollect Implementation Plan
## From Educational Project to Production-Ready Platform

**Document Owner:** Principal Engineer
**Status:** Planning
**Last Updated:** 2025-01-13

---

## 🎯 Executive Summary

This document outlines the transformation of Recollect from an educational multimodal video processing course into a production-ready platform for saving and searching Instagram Reels and YouTube Shorts.

**Vision:** Build a personal video knowledge base where users can save content from social platforms and interact with it using natural language.

**Key Milestones:**
- Phase 1: Address critical scalability bottlenecks (2 weeks)
- Phase 2: MVP with Instagram/YouTube support (3 weeks)
- Phase 3: Production infrastructure (2 weeks)
- Phase 4: Scale & optimization (ongoing)

---

## 🔴 Critical Scalability Issues & Solutions

### Issue #1: Single Uvicorn Worker
**Problem:** API handles only 1 request at a time, causing blocking and poor concurrent user support

**Impact:**
- Can't handle >5 concurrent users
- Video processing blocks all other requests
- Poor user experience

**Solution:**
```yaml
# Phase 1, Week 1
# Update recollect-api/Dockerfile
CMD ["gunicorn", "recollect_api.api:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100"]
```

**Expected Impact:** 4-8x throughput improvement

---

### Issue #2: Pixeltable SQLite Backend
**Problem:** Write locks prevent concurrent video processing, single-writer limitation

**Impact:**
- Only 1 video can be processed at a time
- Multi-user processing fails
- Database locks cause timeouts

**Solution:**
```python
# Phase 1, Week 1
# Update recollect-mcp/src/recollect_mcp/config.py

import pixeltable as pxt
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Existing settings...
    PIXELTABLE_DB_URL: str = "postgresql://recollect:password@postgres:5432/pixeltable"

# Initialize Pixeltable with PostgreSQL
pxt.set_db_url(settings.PIXELTABLE_DB_URL)
```

**Expected Impact:**
- 10-50 concurrent video processing jobs
- Multi-user support enabled

---

### Issue #3: Synchronous Video Processing
**Problem:** Video processing blocks API for 30-60 seconds per video

**Impact:**
- Poor UX (user waits forever)
- API timeouts
- Can't scale to multiple videos

**Solution:**
```python
# Phase 1, Week 2
# Add Celery for async processing

# recollect-api/src/recollect_api/celery_app.py
from celery import Celery

celery_app = Celery(
    'recollect',
    broker='redis://redis:6379/1',
    backend='redis://redis:6379/2'
)

@celery_app.task(bind=True, max_retries=3)
def process_video_task(self, video_path: str):
    """Async video processing"""
    try:
        # Call MCP process_video tool
        result = mcp_client.call_tool("process_video", {"video_path": video_path})
        return {"status": "success", "result": result}
    except Exception as e:
        self.retry(exc=e, countdown=60)

# API endpoint becomes:
@app.post("/process-video")
async def process_video(video_path: str):
    task = process_video_task.delay(video_path)
    return {"task_id": task.id, "status": "processing"}

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    task = celery_app.AsyncResult(task_id)
    return {
        "status": task.state,
        "result": task.result if task.ready() else None
    }
```

**Expected Impact:**
- Non-blocking API (instant response)
- 100+ concurrent video processing jobs
- Better UX with progress tracking

---

### Issue #4: Docker Compose (Single-Host Deployment)
**Problem:** No auto-scaling, no redundancy, single point of failure

**Impact:**
- Can't handle traffic spikes
- Server crash = complete downtime
- Manual scaling only

**Solution - Progressive Approach:**

**Phase 2 (MVP):** Enhanced Docker Compose with health checks
```yaml
# docker-compose.prod.yml
services:
  recollect-api:
    deploy:
      replicas: 3  # Docker Swarm mode
      restart_policy:
        condition: on-failure
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Phase 3 (Production):** Kubernetes Deployment
```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: recollect-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
  template:
    spec:
      containers:
      - name: api
        image: recollect-api:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: recollect-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: recollect-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Expected Impact:**
- Auto-scaling based on load
- Zero-downtime deployments
- High availability (99.9% uptime)

---

## 📋 Implementation Phases

## Phase 1: Foundation & Critical Fixes (2 weeks)

**Goal:** Address all scalability bottlenecks, establish production-ready infrastructure foundation

### Week 1: Infrastructure Setup

#### Day 1-2: Multi-Worker API & Redis Integration
**Tasks:**
- [ ] Add Gunicorn multi-worker configuration
- [ ] Add Redis to docker-compose.yml
- [ ] Add PostgreSQL to docker-compose.yml
- [ ] Update environment variables
- [ ] Add health check endpoints

**Deliverables:**
```yaml
# docker-compose.yml additions
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: recollect
      POSTGRES_USER: recollect
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U recollect"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  redis_data:
  postgres_data:
```

**Testing:**
- Load test with 50 concurrent users
- Verify multi-worker request handling
- Database connection pooling test

---

#### Day 3-4: Memory System Implementation
**Tasks:**
- [ ] Create RedisMemory class
- [ ] Create PostgresArchive class
- [ ] Update Agent to use new memory system
- [ ] Migration script from Pixeltable memory to Redis
- [ ] Add memory expiration policies

**Deliverables:**
```python
# recollect-api/src/recollect_api/memory/redis_memory.py
import redis
import json
from datetime import datetime, timedelta
from typing import List, Dict

class RedisMemory:
    """Hot storage for active conversations"""

    def __init__(self, redis_url: str = "redis://redis:6379/0"):
        self.client = redis.from_url(redis_url, decode_responses=True)

    def add_message(self, session_id: str, role: str, content: str,
                    metadata: Dict = None):
        """Add message to conversation"""
        key = f"session:{session_id}"
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }

        # Add to conversation
        self.client.rpush(key, json.dumps(message))

        # Keep only last 100 messages
        self.client.ltrim(key, -100, -1)

        # Set 7-day expiration
        self.client.expire(key, 86400 * 7)

    def get_latest(self, session_id: str, n: int = 20) -> List[Dict]:
        """Get last N messages"""
        key = f"session:{session_id}"
        messages = self.client.lrange(key, -n, -1)
        return [json.loads(msg) for msg in messages]

    def get_all(self, session_id: str) -> List[Dict]:
        """Get all messages in session"""
        key = f"session:{session_id}"
        messages = self.client.lrange(key, 0, -1)
        return [json.loads(msg) for msg in messages]

    def reset(self, session_id: str):
        """Clear conversation"""
        self.client.delete(f"session:{session_id}")

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists"""
        return self.client.exists(f"session:{session_id}") > 0

# recollect-api/src/recollect_api/memory/postgres_archive.py
import asyncpg
from datetime import datetime
from typing import List, Dict

class PostgresArchive:
    """Cold storage for conversation archives and analytics"""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None

    async def connect(self):
        """Initialize connection pool"""
        self.pool = await asyncpg.create_pool(
            self.db_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        await self._create_tables()

    async def _create_tables(self):
        """Create necessary tables"""
        async with self.pool.acquire() as conn:
            # Conversations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id BIGSERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255),
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_session_created
                ON conversations(session_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_user_created
                ON conversations(user_id, created_at DESC);
            """)

            # Video metadata table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS video_metadata (
                    id BIGSERIAL PRIMARY KEY,
                    video_id VARCHAR(255) UNIQUE NOT NULL,
                    user_id VARCHAR(255),
                    source VARCHAR(50) NOT NULL,  -- 'upload', 'youtube', 'instagram'
                    original_url TEXT,
                    title TEXT,
                    description TEXT,
                    author VARCHAR(255),
                    duration_seconds INT,
                    file_path TEXT NOT NULL,
                    thumbnail_path TEXT,
                    tags TEXT[],
                    created_at TIMESTAMP DEFAULT NOW(),
                    processed_at TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_video_user
                ON video_metadata(user_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_video_source
                ON video_metadata(source, created_at DESC);
            """)

    async def archive_conversation(self, session_id: str, messages: List[Dict],
                                   user_id: str = None):
        """Archive conversation from Redis to Postgres"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for msg in messages:
                    await conn.execute("""
                        INSERT INTO conversations
                        (session_id, user_id, role, content, metadata, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, session_id, user_id, msg['role'], msg['content'],
                         json.dumps(msg.get('metadata', {})),
                         datetime.fromisoformat(msg['timestamp']))

    async def save_video_metadata(self, video_data: Dict):
        """Save video metadata"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO video_metadata
                (video_id, user_id, source, original_url, title, description,
                 author, duration_seconds, file_path, thumbnail_path, tags)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (video_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    processed_at = NOW()
            """, video_data['video_id'], video_data.get('user_id'),
                 video_data['source'], video_data.get('original_url'),
                 video_data.get('title'), video_data.get('description'),
                 video_data.get('author'), video_data.get('duration_seconds'),
                 video_data['file_path'], video_data.get('thumbnail_path'),
                 video_data.get('tags', []))

    async def get_user_videos(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get user's video library"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM video_metadata
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)
            return [dict(row) for row in rows]

# recollect-api/src/recollect_api/memory/__init__.py
from .redis_memory import RedisMemory
from .postgres_archive import PostgresArchive

__all__ = ['RedisMemory', 'PostgresArchive']
```

**Testing:**
- Memory persistence across restarts
- Archival job (Redis → Postgres after 7 days)
- Query performance (<10ms for recent messages)

---

#### Day 5: Pixeltable PostgreSQL Migration
**Tasks:**
- [ ] Configure Pixeltable to use PostgreSQL backend
- [ ] Update video processing pipeline
- [ ] Test concurrent video processing
- [ ] Migration script for existing data

**Deliverables:**
```python
# recollect-mcp/src/recollect_mcp/config.py
import pixeltable as pxt
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Pixeltable configuration
    PIXELTABLE_DB_URL: str = "postgresql://recollect:password@postgres:5432/pixeltable"

    class Config:
        env_file = "recollect-mcp/.env"

settings = Settings()

# Initialize Pixeltable with PostgreSQL
if settings.PIXELTABLE_DB_URL:
    pxt.set_db_url(settings.PIXELTABLE_DB_URL)

# recollect-mcp/scripts/migrate_to_postgres.py
"""
Migration script: SQLite → PostgreSQL
"""
import pixeltable as pxt

def migrate_pixeltable_data():
    """Migrate existing Pixeltable data from SQLite to PostgreSQL"""

    # Set new database URL
    pxt.set_db_url("postgresql://recollect:password@postgres:5432/pixeltable")

    # List all existing tables from SQLite
    # ... migration logic

    print("Migration complete!")

if __name__ == "__main__":
    migrate_pixeltable_data()
```

**Testing:**
- 10 concurrent video processing jobs
- Database connection pool monitoring
- No write lock issues

---

### Week 2: Async Processing & Video Downloader

#### Day 6-7: Celery Integration
**Tasks:**
- [ ] Add Celery + Redis broker to docker-compose
- [ ] Create Celery worker service
- [ ] Migrate video processing to Celery tasks
- [ ] Add task monitoring dashboard (Flower)
- [ ] Update API endpoints for async processing

**Deliverables:**
```yaml
# docker-compose.yml
services:
  celery-worker:
    build: ./recollect-api
    command: celery -A recollect_api.celery_app worker --loglevel=info --concurrency=4
    environment:
      - REDIS_URL=redis://redis:6379/1
      - MCP_SERVER_URL=http://recollect-mcp:9090/mcp
    depends_on:
      - redis
      - recollect-mcp
    volumes:
      - shared_media:/app/shared_media
    deploy:
      replicas: 2  # 2 worker instances

  celery-beat:
    build: ./recollect-api
    command: celery -A recollect_api.celery_app beat --loglevel=info
    environment:
      - REDIS_URL=redis://redis:6379/1
    depends_on:
      - redis

  flower:
    build: ./recollect-api
    command: celery -A recollect_api.celery_app flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - REDIS_URL=redis://redis:6379/1
    depends_on:
      - redis
      - celery-worker
```

```python
# recollect-api/src/recollect_api/celery_app.py
from celery import Celery
from celery.schedules import crontab
import logging

logger = logging.getLogger(__name__)

celery_app = Celery(
    'recollect',
    broker='redis://redis:6379/1',
    backend='redis://redis:6379/2'
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes max
    task_soft_time_limit=1500,  # 25 minute warning
)

@celery_app.task(bind=True, max_retries=3, name='recollect.process_video')
def process_video_task(self, video_path: str, user_id: str = None):
    """Process video asynchronously"""
    try:
        logger.info(f"Processing video: {video_path}")

        # Update task state
        self.update_state(state='PROCESSING', meta={'progress': 0})

        # Call MCP server
        from recollect_api.agent.base_agent import get_mcp_client
        client = get_mcp_client()

        result = client.call_tool("process_video", {
            "video_path": video_path
        })

        self.update_state(state='PROCESSING', meta={'progress': 100})

        logger.info(f"Video processed successfully: {video_path}")
        return {
            "status": "success",
            "video_path": video_path,
            "result": result
        }

    except Exception as e:
        logger.error(f"Error processing video {video_path}: {str(e)}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries * 60)

@celery_app.task(name='recollect.download_video_from_url')
def download_video_task(url: str, user_id: str = None):
    """Download video from URL (Instagram/YouTube)"""
    # Implementation in Day 8-9
    pass

# Periodic tasks
@celery_app.task(name='recollect.archive_old_conversations')
def archive_old_conversations():
    """Archive conversations older than 7 days from Redis to Postgres"""
    from recollect_api.memory import RedisMemory, PostgresArchive
    # Archive logic
    pass

celery_app.conf.beat_schedule = {
    'archive-conversations-daily': {
        'task': 'recollect.archive_old_conversations',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}

# recollect-api/src/recollect_api/api.py updates
from celery.result import AsyncResult

@app.post("/process-video", status_code=202)
async def process_video_async(video_path: str, user_id: str = None):
    """Process video asynchronously"""
    task = process_video_task.delay(video_path, user_id)
    return {
        "task_id": task.id,
        "status": "queued",
        "message": "Video processing started"
    }

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """Check task status"""
    task = AsyncResult(task_id, app=celery_app)

    if task.state == 'PENDING':
        return {"status": "pending", "progress": 0}
    elif task.state == 'PROCESSING':
        return {
            "status": "processing",
            "progress": task.info.get('progress', 0)
        }
    elif task.state == 'SUCCESS':
        return {
            "status": "completed",
            "result": task.result
        }
    elif task.state == 'FAILURE':
        return {
            "status": "failed",
            "error": str(task.info)
        }
    else:
        return {"status": task.state}
```

**Testing:**
- 100 concurrent video processing tasks
- Task failure & retry behavior
- Task progress tracking
- Worker auto-recovery

---

#### Day 8-9: Video Downloader Service
**Tasks:**
- [ ] Add yt-dlp to dependencies
- [ ] Create VideoDownloader service
- [ ] Support Instagram Reels
- [ ] Support YouTube Shorts
- [ ] Add rate limiting & error handling
- [ ] Thumbnail extraction

**Deliverables:**
```python
# recollect-api/requirements.txt (add)
yt-dlp>=2024.1.0

# recollect-api/src/recollect_api/services/video_downloader.py
import yt_dlp
import uuid
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class VideoDownloader:
    """Download videos from Instagram, YouTube, TikTok, etc."""

    def __init__(self, output_dir: str = "shared_media"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

    def download(self, url: str, user_id: Optional[str] = None) -> Dict:
        """
        Download video from URL

        Returns:
            Dict with video metadata and file paths
        """
        video_id = str(uuid.uuid4())
        output_path = str(self.output_dir / f"{video_id}.mp4")

        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_path,
            'quiet': False,
            'no_warnings': False,
            # Convert to mp4 if needed
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            # Extract thumbnail
            'writethumbnail': True,
            'postprocessor_hooks': [self._thumbnail_hook],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Downloading video from: {url}")
                info = ydl.extract_info(url, download=True)

                # Determine source platform
                source = self._detect_source(url, info)

                metadata = {
                    'video_id': video_id,
                    'user_id': user_id,
                    'source': source,
                    'original_url': url,
                    'title': info.get('title'),
                    'description': info.get('description'),
                    'author': info.get('uploader') or info.get('channel'),
                    'duration_seconds': info.get('duration'),
                    'upload_date': info.get('upload_date'),
                    'view_count': info.get('view_count'),
                    'like_count': info.get('like_count'),
                    'file_path': output_path,
                    'thumbnail_path': info.get('thumbnail'),
                    'tags': info.get('tags', []),
                }

                logger.info(f"Video downloaded successfully: {video_id}")
                return metadata

        except Exception as e:
            logger.error(f"Error downloading video from {url}: {str(e)}")
            raise ValueError(f"Failed to download video: {str(e)}")

    def _detect_source(self, url: str, info: Dict) -> str:
        """Detect video source platform"""
        if 'instagram.com' in url:
            return 'instagram'
        elif 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'tiktok.com' in url:
            return 'tiktok'
        elif 'twitter.com' in url or 'x.com' in url:
            return 'twitter'
        else:
            return 'other'

    def _thumbnail_hook(self, d):
        """Post-processor hook for thumbnail extraction"""
        if d['status'] == 'finished':
            logger.info(f"Thumbnail extracted: {d.get('filepath')}")

# Celery task
@celery_app.task(bind=True, max_retries=3, name='recollect.download_video_from_url')
def download_video_task(self, url: str, user_id: str = None):
    """Download video from URL asynchronously"""
    try:
        downloader = VideoDownloader()

        # Download video
        self.update_state(state='DOWNLOADING', meta={'progress': 0})
        metadata = downloader.download(url, user_id)

        # Save metadata to Postgres
        self.update_state(state='SAVING_METADATA', meta={'progress': 50})
        from recollect_api.memory import PostgresArchive
        archive = PostgresArchive(settings.POSTGRES_URL)
        await archive.save_video_metadata(metadata)

        # Process video with Pixeltable
        self.update_state(state='PROCESSING_VIDEO', meta={'progress': 60})
        process_result = process_video_task.delay(metadata['file_path'], user_id)

        return {
            "status": "success",
            "metadata": metadata,
            "processing_task_id": process_result.id
        }

    except Exception as e:
        logger.error(f"Error in download_video_task: {str(e)}")
        raise self.retry(exc=e, countdown=2 ** self.request.retries * 60)

# API endpoint
@app.post("/upload-video-from-url", status_code=202)
async def upload_video_from_url(url: str, user_id: str = None):
    """Download and process video from URL"""

    # Validate URL
    supported_platforms = ['instagram.com', 'youtube.com', 'youtu.be', 'tiktok.com']
    if not any(platform in url for platform in supported_platforms):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform. Supported: {', '.join(supported_platforms)}"
        )

    # Start download task
    task = download_video_task.delay(url, user_id)

    return {
        "task_id": task.id,
        "status": "downloading",
        "message": "Video download started"
    }
```

**Testing:**
- Download from Instagram (public reels)
- Download from YouTube Shorts
- Rate limiting (respect platform limits)
- Error handling (private videos, deleted content)
- Thumbnail extraction

---

#### Day 10: Testing & Documentation
**Tasks:**
- [ ] Integration tests for all Phase 1 components
- [ ] Load testing (100 concurrent users)
- [ ] Update API documentation
- [ ] Create Phase 1 deployment guide
- [ ] Performance benchmarks

**Deliverables:**
- Test coverage >80%
- Load test results document
- Updated API docs (OpenAPI/Swagger)
- Deployment runbook

**Success Metrics:**
- ✅ 4x throughput improvement (API)
- ✅ 100+ concurrent video processing jobs
- ✅ <10ms memory retrieval
- ✅ Non-blocking video processing

---

## Phase 2: MVP Features & User Experience (3 weeks)

**Goal:** Build core Instagram/YouTube features with excellent UX

### Week 3: Frontend Enhancement

#### Day 11-12: URL Upload UI
**Tasks:**
- [ ] Add URL input component
- [ ] Support drag-and-drop URLs
- [ ] Real-time progress indicators
- [ ] Error handling & user feedback
- [ ] Platform icon detection

**Deliverables:**
```tsx
// recollect-ui/src/components/VideoUpload.tsx
import { useState } from 'react';
import { Upload, Link, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';

export function VideoUpload() {
  const [url, setUrl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);

  const handleUrlSubmit = async () => {
    if (!url) return;

    setUploading(true);
    try {
      const response = await fetch('http://localhost:8080/upload-video-from-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });

      const data = await response.json();
      setTaskId(data.task_id);

      toast.success('Video download started!');

      // Poll for status
      pollTaskStatus(data.task_id);

    } catch (error) {
      toast.error('Failed to download video');
    } finally {
      setUploading(false);
    }
  };

  const pollTaskStatus = async (taskId: string) => {
    const interval = setInterval(async () => {
      const response = await fetch(`http://localhost:8080/task-status/${taskId}`);
      const data = await response.json();

      if (data.status === 'completed') {
        clearInterval(interval);
        toast.success('Video processed successfully!');
        // Refresh video library
      } else if (data.status === 'failed') {
        clearInterval(interval);
        toast.error('Video processing failed');
      }
    }, 2000);
  };

  return (
    <Tabs defaultValue="url">
      <TabsList>
        <TabsTrigger value="url">
          <Link className="mr-2 h-4 w-4" />
          From URL
        </TabsTrigger>
        <TabsTrigger value="file">
          <Upload className="mr-2 h-4 w-4" />
          Upload File
        </TabsTrigger>
      </TabsList>

      <TabsContent value="url" className="space-y-4">
        <div className="flex gap-2">
          <Input
            placeholder="Paste Instagram Reel or YouTube Short URL..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={uploading}
          />
          <Button onClick={handleUrlSubmit} disabled={uploading}>
            {uploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Downloading
              </>
            ) : (
              'Download'
            )}
          </Button>
        </div>

        <p className="text-sm text-muted-foreground">
          Supported: Instagram Reels, YouTube Shorts, TikTok
        </p>
      </TabsContent>

      <TabsContent value="file">
        {/* Existing file upload component */}
      </TabsContent>
    </Tabs>
  );
}
```

---

#### Day 13-14: Video Library & Management
**Tasks:**
- [ ] Video library grid view
- [ ] Filter by source (Instagram/YouTube/Upload)
- [ ] Search by title/author
- [ ] Delete video functionality
- [ ] Bulk operations (select multiple)

**Deliverables:**
```tsx
// recollect-ui/src/components/VideoLibrary.tsx
import { useQuery } from '@tanstack/react-query';
import { Instagram, Youtube, Upload } from 'lucide-react';

export function VideoLibrary() {
  const { data: videos, isLoading } = useQuery({
    queryKey: ['videos'],
    queryFn: async () => {
      const response = await fetch('http://localhost:8080/videos');
      return response.json();
    }
  });

  const getSourceIcon = (source: string) => {
    switch (source) {
      case 'instagram':
        return <Instagram className="h-4 w-4" />;
      case 'youtube':
        return <Youtube className="h-4 w-4" />;
      default:
        return <Upload className="h-4 w-4" />;
    }
  };

  return (
    <div className="grid grid-cols-3 gap-4">
      {videos?.map((video) => (
        <div key={video.id} className="border rounded-lg overflow-hidden">
          <img src={video.thumbnail_path} alt={video.title} />
          <div className="p-4">
            <div className="flex items-center gap-2">
              {getSourceIcon(video.source)}
              <h3 className="font-medium truncate">{video.title}</h3>
            </div>
            <p className="text-sm text-muted-foreground">{video.author}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
```

---

#### Day 15: Enhanced Chat Experience
**Tasks:**
- [ ] Multi-video context (reference videos by name)
- [ ] Video preview in chat
- [ ] Quick actions (re-process, delete)
- [ ] Session management UI

---

### Week 4: Backend Features

#### Day 16-17: User Authentication (Optional but Recommended)
**Tasks:**
- [ ] Add JWT authentication
- [ ] User registration/login endpoints
- [ ] Session-to-user mapping
- [ ] Protected routes

**Deliverables:**
```python
# recollect-api/src/recollect_api/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

SECRET_KEY = "your-secret-key"  # Move to env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")

# Usage in endpoints
@app.get("/videos")
async def get_user_videos(user_id: str = Depends(get_current_user)):
    """Get user's video library"""
    archive = PostgresArchive(settings.POSTGRES_URL)
    videos = await archive.get_user_videos(user_id)
    return videos
```

---

#### Day 18-19: Advanced Video Features
**Tasks:**
- [ ] Video collections/playlists
- [ ] Tags and categorization
- [ ] Favorite videos
- [ ] Video sharing (generate shareable links)
- [ ] Export conversation as markdown

---

#### Day 20-21: Search & Discovery
**Tasks:**
- [ ] Full-text search across video metadata
- [ ] "Find similar videos" feature
- [ ] Trending topics from user's library
- [ ] Auto-tagging based on content

---

### Week 5: Polish & Testing

#### Day 22-23: Performance Optimization
**Tasks:**
- [ ] Database query optimization
- [ ] Redis caching for video metadata
- [ ] Lazy loading for video library
- [ ] Image optimization (thumbnails)
- [ ] API response compression

---

#### Day 24-25: End-to-End Testing
**Tasks:**
- [ ] User flow testing
- [ ] Error scenario testing
- [ ] Cross-browser testing
- [ ] Mobile responsiveness
- [ ] Accessibility audit

---

#### Day 26: MVP Launch Prep
**Tasks:**
- [ ] User documentation
- [ ] Demo video
- [ ] Deployment to staging
- [ ] Beta user testing
- [ ] Bug fixes

**Phase 2 Success Metrics:**
- ✅ Instagram/YouTube downloads working
- ✅ Video library with 100+ videos
- ✅ <3 second chat response time
- ✅ >95% uptime

---

## Phase 3: Production Infrastructure (2 weeks)

**Goal:** Production-ready deployment with monitoring, security, and scalability

### Week 6: DevOps & Infrastructure

#### Day 27-28: Monitoring & Observability
**Tasks:**
- [ ] Add Prometheus metrics
- [ ] Grafana dashboards
- [ ] Sentry error tracking
- [ ] Log aggregation (ELK or Loki)
- [ ] Uptime monitoring

**Deliverables:**
```yaml
# docker-compose.prod.yml additions
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    volumes:
      - loki_data:/loki

volumes:
  prometheus_data:
  grafana_data:
  loki_data:
```

```python
# recollect-api/src/recollect_api/metrics.py
from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
request_count = Counter('recollect_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('recollect_request_duration_seconds', 'Request duration')
active_sessions = Gauge('recollect_active_sessions', 'Active chat sessions')
video_processing_queue = Gauge('recollect_video_queue_size', 'Videos in processing queue')

# Middleware
@app.middleware("http")
async def metrics_middleware(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    request_duration.observe(duration)

    return response
```

---

#### Day 29-30: Security Hardening
**Tasks:**
- [ ] Rate limiting (per user, per IP)
- [ ] Input validation & sanitization
- [ ] CORS configuration
- [ ] HTTPS setup (Let's Encrypt)
- [ ] Secrets management (Vault/AWS Secrets Manager)
- [ ] Security headers
- [ ] SQL injection prevention audit

**Deliverables:**
```python
# recollect-api/src/recollect_api/middleware.py
from fastapi import Request, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/chat")
@limiter.limit("20/minute")  # 20 requests per minute per IP
async def chat(request: Request, message: str):
    # ... chat logic
    pass

@app.post("/upload-video-from-url")
@limiter.limit("10/hour")  # 10 video downloads per hour
async def upload_video_from_url(request: Request, url: str):
    # ... download logic
    pass

# Security headers
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response
```

---

#### Day 31-32: Backup & Disaster Recovery
**Tasks:**
- [ ] Automated PostgreSQL backups
- [ ] Redis persistence configuration
- [ ] S3 video backup strategy
- [ ] Restore procedures documentation
- [ ] Backup monitoring & alerting

---

#### Day 33-34: CI/CD Pipeline
**Tasks:**
- [ ] GitHub Actions workflow
- [ ] Automated testing on PR
- [ ] Docker image building
- [ ] Staging deployment
- [ ] Production deployment (with approval)

**Deliverables:**
```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd recollect-api
          pip install -e .
          pip install pytest pytest-cov

      - name: Run tests
        run: |
          cd recollect-api
          pytest --cov=recollect_api tests/

      - name: Upload coverage
        uses: codecov/codecov-action@v3

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3

      - name: Build Docker images
        run: |
          docker build -t recollect-api:${{ github.sha }} ./recollect-api
          docker build -t recollect-mcp:${{ github.sha }} ./recollect-mcp
          docker build -t recollect-ui:${{ github.sha }} ./recollect-ui

      - name: Push to registry
        run: |
          # Push to Docker Hub / ECR / GCR
          docker push recollect-api:${{ github.sha }}

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        run: |
          # SSH to staging server and deploy
          # Or use Kubernetes/ECS deployment

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://recollect.ai
    steps:
      - name: Deploy to production
        run: |
          # Production deployment
          # Requires manual approval in GitHub
```

---

### Week 7: Kubernetes Migration (Optional - for scale)

#### Day 35-38: Kubernetes Setup
**Tasks:**
- [ ] Create Kubernetes manifests
- [ ] Helm charts for easy deployment
- [ ] Horizontal Pod Autoscaling
- [ ] Ingress controller setup
- [ ] Persistent volume management
- [ ] Secrets management

**Deliverables:**
```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: recollect-api
  namespace: recollect
spec:
  replicas: 3
  selector:
    matchLabels:
      app: recollect-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: recollect-api
    spec:
      containers:
      - name: api
        image: recollect-api:latest
        ports:
        - containerPort: 8080
        env:
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: recollect-config
              key: redis_url
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: recollect-secrets
              key: postgres_password
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: recollect-api
  namespace: recollect
spec:
  selector:
    app: recollect-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: recollect-api-hpa
  namespace: recollect
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: recollect-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

#### Day 39-40: Load Testing & Optimization
**Tasks:**
- [ ] k6 load testing scripts
- [ ] 10K concurrent users test
- [ ] Database query optimization
- [ ] CDN setup for static assets
- [ ] Performance tuning

**Deliverables:**
```javascript
// k6-load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp up to 100 users
    { duration: '5m', target: 1000 },  // Ramp up to 1000 users
    { duration: '10m', target: 1000 }, // Stay at 1000 users
    { duration: '2m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests must complete below 500ms
    http_req_failed: ['rate<0.01'],   // Error rate must be below 1%
  },
};

export default function () {
  // Test chat endpoint
  const chatResponse = http.post('http://localhost:8080/chat', JSON.stringify({
    message: 'Show me cooking videos',
    session_id: `session-${__VU}`,
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(chatResponse, {
    'chat status is 200': (r) => r.status === 200,
    'chat response time < 500ms': (r) => r.timings.duration < 500,
  });

  sleep(1);
}
```

---

## Phase 4: Advanced Features & Scale (Ongoing)

**Goal:** Enterprise features, advanced AI capabilities, multi-tenancy

### Month 2+: Advanced Features

#### Mem0 Integration (Optional)
**When to add:** After 1,000+ active users with requests like "remember when I..."

**Tasks:**
- [ ] Integrate Mem0 API
- [ ] Extract long-term user preferences
- [ ] Cross-session entity tracking
- [ ] Personalized recommendations

---

#### Advanced Search
**Tasks:**
- [ ] Elasticsearch/OpenSearch integration
- [ ] Full-text search across transcripts
- [ ] Semantic search with embeddings
- [ ] Faceted search (by date, source, duration)

---

#### Multi-tenancy & Teams
**Tasks:**
- [ ] Organization accounts
- [ ] Shared video libraries
- [ ] Permission management
- [ ] Team collaboration features

---

#### Analytics & Insights
**Tasks:**
- [ ] User engagement metrics
- [ ] Most-watched topics
- [ ] Search analytics
- [ ] Usage reports

---

## 📊 Success Metrics by Phase

| Phase | Metric | Target |
|-------|--------|--------|
| Phase 1 | API Throughput | 4x improvement |
| Phase 1 | Concurrent Video Processing | 100+ jobs |
| Phase 1 | Memory Retrieval | <10ms |
| Phase 2 | Video Downloads | Instagram + YouTube working |
| Phase 2 | User Satisfaction | >4.5/5 rating |
| Phase 2 | Uptime | >95% |
| Phase 3 | Load Test | 10K concurrent users |
| Phase 3 | Error Rate | <0.1% |
| Phase 3 | P95 Response Time | <500ms |
| Phase 4 | Active Users | 10K+ |
| Phase 4 | Videos Processed | 100K+ |

---

## 🚨 Risk Mitigation

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Instagram blocks scraping | High | Add authentication support, rate limiting, fallback to manual upload |
| Video processing costs too high | High | Optimize frame sampling, use cheaper models, implement usage limits |
| Database becomes bottleneck | Medium | Read replicas, connection pooling, query optimization |
| Celery workers crash | Medium | Auto-restart policies, task retry logic, dead letter queues |
| Memory consumption spikes | Medium | Resource limits, memory profiling, garbage collection tuning |

### Business Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| DMCA takedown requests | High | Clear terms of service, personal use only disclaimer, quick response process |
| API rate limits hit | Medium | User education, queue management, tier-based limits |
| Storage costs grow | Medium | Compression, retention policies, user quotas |

---

## 💰 Cost Estimation

### Phase 1-2 (MVP)
- **Infrastructure:** $100-200/month
  - Redis Cloud: $20
  - PostgreSQL (Supabase/Railway): $25
  - Compute (Railway/Render): $50-100
  - S3 storage: $10-20
- **API Costs:** $100-300/month
  - OpenAI: $50-150
  - Groq: $0-100
- **Total:** ~$200-500/month

### Phase 3-4 (Production, 10K users)
- **Infrastructure:** $500-1500/month
  - Kubernetes cluster: $200-500
  - Redis Cluster: $100-200
  - PostgreSQL: $200-400
  - S3 + CDN: $100-200
  - Monitoring: $50-100
- **API Costs:** $1000-3000/month
- **Total:** ~$1,500-4,500/month

---

## 🎯 Next Steps

### Immediate Actions (This Week)
1. ✅ Review and approve implementation plan
2. ⬜ Create GitHub project board with all tasks
3. ⬜ Set up development environment
4. ⬜ Begin Phase 1, Day 1 tasks
5. ⬜ Schedule weekly sync meetings

### Week 1 Deliverables
- [ ] Multi-worker API running
- [ ] Redis + PostgreSQL integrated
- [ ] New memory system implemented
- [ ] Load test showing 4x improvement

---

## 📚 Documentation Requirements

Each phase must deliver:
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Deployment runbooks
- [ ] Architecture diagrams
- [ ] Testing documentation
- [ ] User guides

---

## 🔄 Agile Process

### Sprint Structure
- **Sprint Length:** 2 weeks
- **Daily Standups:** 15 minutes
- **Sprint Planning:** Start of sprint
- **Sprint Review:** End of sprint
- **Retrospective:** After review

### Definition of Done
- [ ] Code reviewed and approved
- [ ] Tests written and passing (>80% coverage)
- [ ] Documentation updated
- [ ] Deployed to staging
- [ ] Acceptance criteria met

---

**Principal Engineer Sign-off:** Ready for implementation

**Next Review Date:** End of Phase 1 (2 weeks)

**Questions/Concerns:** Open GitHub discussion thread
