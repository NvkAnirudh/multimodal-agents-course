# Recollect Implementation Plan
## Consumer App for Organizing & Searching Social Media Videos

**Document Owner:** Product & Engineering
**Status:** Active Development
**Last Updated:** 2025-11-14

---

## 🎯 Executive Summary

**Vision:** Build the "Notion for your saved videos" - a personal video knowledge base where users can save Instagram Reels, YouTube Shorts, and LinkedIn videos, then search them using natural language.

**The Problem We're Solving:**
- Users save 100s of reels/shorts but can never find them again
- Platform search only works on captions (useless for visual content)
- Scrolling through saved collections takes forever
- No way to search by what's actually IN the video

**Our Solution:**
- One-click save from browser (extension) or mobile (share sheet)
- AI-powered semantic search ("pasta recipe with cherry tomatoes")
- Auto-categorization and tagging
- Search by speech, visuals, or topics
- Works across Instagram, YouTube, TikTok, LinkedIn

**Target Users:**
- Home cooks (save recipe reels)
- Fitness enthusiasts (workout videos)
- Entrepreneurs (business tips)
- Designers (inspiration)
- Anyone who saves 50+ videos/month

---

## 🏗️ What We're Building

### Product Overview

**Core Features:**
1. **Save Videos** - Browser extension + bookmarklet for desktop, share sheet for mobile
2. **Process & Index** - Extract transcripts, captions, embeddings automatically
3. **Search Everything** - Natural language search across all content
4. **Organize** - Auto-categories, manual tags, collections
5. **Chat Interface** - Ask questions about your video library

**Technical Architecture:**
```
User Flow:
1. User sees reel on Instagram
2. Clicks "Save to Recollect" (browser extension)
3. Backend downloads & processes video
4. User searches: "that pasta recipe with tomatoes"
5. Gets exact video + timestamp

Tech Stack:
├─ Frontend: Next.js + Tailwind (web app)
├─ Extension: Chrome/Firefox extension
├─ Backend: FastAPI + Celery (already built ✅)
├─ Processing: Video extraction + embeddings (already built ✅)
├─ Storage: PostgreSQL + Vector DB
└─ Hosting: Railway/Render (MVP) → AWS (scale)
```

---

## ✅ What's Already Done (Phase 0)

### Completed Work:
- ✅ **Video processing backend** - Pixeltable pipeline for extracting frames, audio, transcripts
- ✅ **Embeddings generation** - CLIP for frames, OpenAI for text
- ✅ **Vector search** - Similarity search across frames and transcripts
- ✅ **Chat interface** - Basic Q&A about videos
- ✅ **Persistent storage** - Fixed Pixeltable cache directory issue
- ✅ **Async processing** - Celery + RabbitMQ for background jobs
- ✅ **Docker infrastructure** - Multi-container setup with Redis, PostgreSQL

### What Works Right Now:
```bash
# Current capabilities:
1. Upload video file → processes in ~3 minutes
2. Search by text: "What is this video about?"
3. Search by image: Upload screenshot → find similar frames
4. Extract clips based on queries
5. Transcription + caption generation
```

**Current Limitations:**
- **Storage:** ~70 MB per video (needs 10x reduction → 7 MB)
- **Processing:** ~3.4 minutes per video (needs 3x speedup → 1 min)
- **Architecture:** Pixeltable with embedded PostgreSQL (needs migration to Vector DB)

### Migration Required: Pixeltable → PostgreSQL + Vector DB

**Why migrate?**
1. **Storage overhead:** Pixeltable's embedded PostgreSQL adds 48 MB overhead per video
2. **Frame storage:** Storing frame images (5.8 MB) when we only need embeddings (410 KB)
3. **Re-encoded videos:** Keeping re-encoded videos (8.7 MB) after processing
4. **Scalability:** Embedded PostgreSQL not designed for multi-user production workloads
5. **Cost:** 70 MB/video = $16K/month for 100K users × 100 videos

**New Architecture:**
```
Current (Pixeltable):                  New (Vector DB):
├─ Pixeltable (70 MB/video)           ├─ PostgreSQL (metadata only, ~100 KB)
│  ├─ Embedded PostgreSQL (48 MB)     ├─ Pinecone/Qdrant (embeddings, ~310 KB)
│  ├─ Frame images (5.8 MB)           │  ├─ Frame embeddings (20 × 512 dim)
│  ├─ Re-encoded video (8.7 MB)       │  ├─ Caption embeddings (20 × 1536 dim)
│  └─ Embeddings (410 KB)             │  └─ Audio embeddings (13 × 1536 dim)
│                                     └─ S3/MinIO (original video only, ~5 MB)
└─ Total: 70 MB                       └─ Total: ~7 MB (10x reduction)
```

**Migration planned in Phase 3** (see detailed implementation below)

---

## 📋 Implementation Phases

## Phase 1: User Save Flow & Download Pipeline (2 weeks) ⏳

**Goal:** Enable users to save videos from Instagram/YouTube/LinkedIn

### Week 1: Video Download Service

#### Day 1-2: yt-dlp Integration ✅ PRIORITY
**Tasks:**
- [x] Add yt-dlp to dependencies
- [ ] Create VideoDownloader service class
- [ ] Support Instagram Reels downloads
- [ ] Support YouTube Shorts downloads
- [ ] Support LinkedIn video posts
- [ ] Error handling & retry logic
- [ ] Thumbnail extraction

**Implementation:**
```python
# recollect-api/src/recollect_api/services/video_downloader.py
import yt_dlp
import uuid
from pathlib import Path
from typing import Dict, Optional

class VideoDownloader:
    """Download videos from Instagram, YouTube, LinkedIn"""

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
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'writethumbnail': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                # Detect platform
                source = self._detect_source(url)

                return {
                    'video_id': video_id,
                    'user_id': user_id,
                    'source': source,  # 'instagram', 'youtube', 'linkedin'
                    'original_url': url,
                    'title': info.get('title'),
                    'description': info.get('description'),
                    'author': info.get('uploader'),
                    'duration_seconds': info.get('duration'),
                    'file_path': output_path,
                    'thumbnail_path': info.get('thumbnail'),
                    'tags': info.get('tags', []),
                }

        except Exception as e:
            raise ValueError(f"Failed to download video: {str(e)}")

    def _detect_source(self, url: str) -> str:
        """Detect video source platform"""
        if 'instagram.com' in url:
            return 'instagram'
        elif 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'linkedin.com' in url:
            return 'linkedin'
        elif 'tiktok.com' in url:
            return 'tiktok'
        return 'other'
```

**Testing:**
- [ ] Download Instagram Reel (public)
- [ ] Download YouTube Short
- [ ] Download LinkedIn video
- [ ] Handle private videos (should fail gracefully)
- [ ] Handle deleted content

---

#### Day 3-4: Celery Task for Download + Process
**Tasks:**
- [ ] Create combined Celery task: download → process → store
- [ ] Add task progress tracking
- [ ] Store video metadata in PostgreSQL
- [ ] Update API endpoints

**Implementation:**
```python
# recollect-api/src/recollect_api/tasks.py
from celery import chain
from recollect_api.celery_app import celery_app
from recollect_api.services.video_downloader import VideoDownloader

@celery_app.task(bind=True, name='recollect.download_and_process_video')
def download_and_process_video(self, url: str, user_id: str = None):
    """
    Download video from URL, then process it

    Flow:
    1. Download video using yt-dlp
    2. Save metadata to PostgreSQL
    3. Process video with Pixeltable (frames + audio)
    4. Store embeddings in Vector DB
    """
    try:
        # Step 1: Download
        self.update_state(state='DOWNLOADING', meta={'progress': 10})
        downloader = VideoDownloader()
        metadata = downloader.download(url, user_id)

        # Step 2: Save metadata
        self.update_state(state='SAVING_METADATA', meta={'progress': 30})
        # TODO: Save to PostgreSQL

        # Step 3: Process video (call existing MCP tool)
        self.update_state(state='PROCESSING_VIDEO', meta={'progress': 40})
        from recollect_api.agent.base_agent import get_mcp_client
        client = get_mcp_client()

        result = client.call_tool("process_video", {
            "video_path": metadata['file_path']
        })

        self.update_state(state='COMPLETED', meta={'progress': 100})

        return {
            "status": "success",
            "video_id": metadata['video_id'],
            "metadata": metadata,
            "processing_result": result
        }

    except Exception as e:
        self.update_state(state='FAILED', meta={'error': str(e)})
        raise

# API endpoint
@app.post("/save-video", status_code=202)
async def save_video_from_url(url: str, user_id: str = None):
    """
    Save video from Instagram/YouTube/LinkedIn URL

    Example:
        POST /save-video
        {"url": "https://www.instagram.com/reel/xyz", "user_id": "user123"}
    """
    # Validate URL
    supported_platforms = ['instagram.com', 'youtube.com', 'youtu.be',
                          'linkedin.com', 'tiktok.com']
    if not any(platform in url for platform in supported_platforms):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform. Supported: {', '.join(supported_platforms)}"
        )

    # Start task
    task = download_and_process_video.delay(url, user_id)

    return {
        "task_id": task.id,
        "status": "processing",
        "message": "Video download and processing started",
        "estimated_time": "2-3 minutes"
    }
```

---

#### Day 5: Database Schema for Video Library
**Tasks:**
- [ ] Create PostgreSQL schema for video metadata
- [ ] Add user-video relationship
- [ ] Add tags and collections support
- [ ] Migration scripts

**Schema:**
```sql
-- Users table (basic for now)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Videos table
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Video metadata
    source VARCHAR(50) NOT NULL,  -- 'instagram', 'youtube', 'linkedin'
    original_url TEXT NOT NULL,
    file_path TEXT NOT NULL,
    thumbnail_path TEXT,

    -- Content metadata
    title TEXT,
    description TEXT,
    author VARCHAR(255),
    duration_seconds INT,

    -- Processing status
    processing_status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    processed_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Search optimization
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(description, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(author, '')), 'C')
    ) STORED
);

CREATE INDEX idx_videos_user_id ON videos(user_id, created_at DESC);
CREATE INDEX idx_videos_source ON videos(source);
CREATE INDEX idx_videos_search_vector ON videos USING GIN(search_vector);

-- Tags table
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    color VARCHAR(7),  -- hex color
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- Video-Tag mapping
CREATE TABLE video_tags (
    video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (video_id, tag_id)
);

-- Collections (playlists)
CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    thumbnail_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Collection-Video mapping
CREATE TABLE collection_videos (
    collection_id UUID REFERENCES collections(id) ON DELETE CASCADE,
    video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
    position INT NOT NULL,  -- order in collection
    added_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (collection_id, video_id)
);

CREATE INDEX idx_collection_videos_position ON collection_videos(collection_id, position);
```

**API Endpoints:**
```python
@app.get("/videos")
async def get_user_videos(
    user_id: str,
    source: Optional[str] = None,  # filter by platform
    tag: Optional[str] = None,     # filter by tag
    limit: int = 50,
    offset: int = 0
):
    """Get user's video library"""
    # TODO: Query PostgreSQL
    pass

@app.get("/videos/{video_id}")
async def get_video_details(video_id: str, user_id: str):
    """Get detailed video info"""
    pass

@app.delete("/videos/{video_id}")
async def delete_video(video_id: str, user_id: str):
    """Delete video from library"""
    pass

@app.post("/videos/{video_id}/tags")
async def add_tag_to_video(video_id: str, tag_name: str, user_id: str):
    """Add tag to video"""
    pass
```

---

### Week 2: Browser Extension & Bookmarklet

#### Day 6-7: Bookmarklet MVP (Fastest Path)
**Goal:** Get something users can use TODAY

**Tasks:**
- [ ] Create simple web form for URL input
- [ ] Create bookmarklet JavaScript
- [ ] Add to website with drag-and-drop instructions
- [ ] Test on Instagram, YouTube, LinkedIn

**Implementation:**
```html
<!-- recollect-ui/public/bookmarklet.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Recollect - Save This Video</title>
</head>
<body>
    <h1>Save to Recollect</h1>
    <p>Drag this button to your bookmarks bar:</p>

    <a href="javascript:(function(){
        var url = window.location.href;
        var popup = window.open(
            'https://recollect.app/save?url=' + encodeURIComponent(url),
            'RecollectSave',
            'width=600,height=400'
        );
    })();"
       class="bookmarklet-button">
        📹 Save to Recollect
    </a>

    <h2>Or paste a URL:</h2>
    <form id="saveForm">
        <input type="url"
               id="videoUrl"
               placeholder="https://www.instagram.com/reel/..."
               required />
        <button type="submit">Save Video</button>
    </form>

    <div id="status"></div>

    <script>
        document.getElementById('saveForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const url = document.getElementById('videoUrl').value;
            const statusDiv = document.getElementById('status');

            statusDiv.textContent = 'Saving...';

            try {
                const response = await fetch('http://localhost:8080/save-video', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });

                const data = await response.json();
                statusDiv.textContent = `✅ Video saved! Processing... (${data.estimated_time})`;

                // Poll for completion
                pollTaskStatus(data.task_id);

            } catch (error) {
                statusDiv.textContent = '❌ Error saving video: ' + error.message;
            }
        });

        async function pollTaskStatus(taskId) {
            const interval = setInterval(async () => {
                const response = await fetch(`http://localhost:8080/task-status/${taskId}`);
                const data = await response.json();

                if (data.status === 'COMPLETED') {
                    clearInterval(interval);
                    document.getElementById('status').textContent =
                        '✅ Video ready! You can search it now.';
                } else if (data.status === 'FAILED') {
                    clearInterval(interval);
                    document.getElementById('status').textContent =
                        '❌ Processing failed: ' + data.error;
                }
            }, 3000);
        }
    </script>
</body>
</html>
```

**User Flow:**
1. User drags bookmarklet to toolbar
2. User watches reel on Instagram
3. User clicks bookmarklet
4. Popup opens confirming save
5. Backend processes in background
6. User gets notification when ready

---

#### Day 8-10: Chrome Extension (Better UX)
**Tasks:**
- [ ] Create Chrome extension manifest
- [ ] Content script to detect Instagram/YouTube/LinkedIn
- [ ] Inject "Save to Recollect" button directly on pages
- [ ] Background script for API calls
- [ ] Popup UI for quick video library access
- [ ] Submit to Chrome Web Store (approval takes 1-2 weeks)

**Extension Structure:**
```
recollect-extension/
├── manifest.json
├── background.js          # Handle API calls, notifications
├── content-scripts/
│   ├── instagram.js      # Inject button on Instagram
│   ├── youtube.js        # Inject button on YouTube
│   └── linkedin.js       # Inject button on LinkedIn
├── popup/
│   ├── popup.html        # Extension popup UI
│   ├── popup.js
│   └── popup.css
└── icons/
    ├── icon16.png
    ├── icon48.png
    └── icon128.png
```

**manifest.json:**
```json
{
  "manifest_version": 3,
  "name": "Recollect - Save & Search Your Videos",
  "version": "1.0.0",
  "description": "Save Instagram Reels, YouTube Shorts, and LinkedIn videos. Search them with AI.",

  "permissions": [
    "activeTab",
    "storage",
    "notifications"
  ],

  "host_permissions": [
    "https://www.instagram.com/*",
    "https://www.youtube.com/*",
    "https://www.linkedin.com/*"
  ],

  "background": {
    "service_worker": "background.js"
  },

  "content_scripts": [
    {
      "matches": ["https://www.instagram.com/*"],
      "js": ["content-scripts/instagram.js"],
      "css": ["content-scripts/styles.css"]
    },
    {
      "matches": ["https://www.youtube.com/*"],
      "js": ["content-scripts/youtube.js"],
      "css": ["content-scripts/styles.css"]
    },
    {
      "matches": ["https://www.linkedin.com/*"],
      "js": ["content-scripts/linkedin.js"],
      "css": ["content-scripts/styles.css"]
    }
  ],

  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },

  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  }
}
```

**content-scripts/instagram.js:**
```javascript
// Inject "Save to Recollect" button on Instagram Reels
(function() {
    'use strict';

    // Wait for reel to load
    const observer = new MutationObserver(() => {
        const actionButtons = document.querySelector('section[role="complementary"]');

        if (actionButtons && !document.getElementById('recollect-save-btn')) {
            injectSaveButton(actionButtons);
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    function injectSaveButton(container) {
        const saveBtn = document.createElement('div');
        saveBtn.id = 'recollect-save-btn';
        saveBtn.className = 'recollect-btn';
        saveBtn.innerHTML = `
            <button>
                <svg><!-- Bookmark icon --></svg>
                <span>Save to Recollect</span>
            </button>
        `;

        saveBtn.addEventListener('click', async () => {
            const url = window.location.href;

            // Send to background script
            chrome.runtime.sendMessage({
                action: 'saveVideo',
                url: url,
                source: 'instagram'
            }, (response) => {
                if (response.success) {
                    saveBtn.innerHTML = '✅ Saved!';
                    setTimeout(() => {
                        saveBtn.innerHTML = 'Save to Recollect';
                    }, 2000);
                }
            });
        });

        container.prepend(saveBtn);
    }
})();
```

**background.js:**
```javascript
// Handle save requests from content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'saveVideo') {
        saveVideoToRecollect(request.url, request.source)
            .then(() => {
                sendResponse({success: true});

                // Show notification
                chrome.notifications.create({
                    type: 'basic',
                    iconUrl: 'icons/icon48.png',
                    title: 'Video Saved!',
                    message: 'Processing your video... You\'ll be able to search it in 2-3 minutes.'
                });
            })
            .catch((error) => {
                sendResponse({success: false, error: error.message});
            });

        return true;  // Keep message channel open for async response
    }
});

async function saveVideoToRecollect(url, source) {
    const API_URL = 'https://api.recollect.app';  // or http://localhost:8080

    const response = await fetch(`${API_URL}/save-video`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${await getAuthToken()}`
        },
        body: JSON.stringify({url, source})
    });

    if (!response.ok) {
        throw new Error('Failed to save video');
    }

    return await response.json();
}

async function getAuthToken() {
    // Get from chrome.storage
    const data = await chrome.storage.local.get(['authToken']);
    return data.authToken || null;
}
```

**popup/popup.html:**
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {
            width: 400px;
            padding: 20px;
            font-family: system-ui;
        }
        .search-box {
            width: 100%;
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 8px;
        }
        .video-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-top: 20px;
        }
        .video-card img {
            width: 100%;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <h2>Recollect</h2>

    <input type="text"
           class="search-box"
           placeholder="Search your videos..."
           id="searchInput" />

    <div id="videoGrid" class="video-grid">
        <!-- Videos will be loaded here -->
    </div>

    <script src="popup.js"></script>
</body>
</html>
```

---

**Phase 1 Success Metrics:**
- ✅ Bookmarklet working on Instagram/YouTube/LinkedIn
- ✅ Videos downloading and processing automatically
- ✅ Chrome extension submitted to Web Store
- ✅ 10 beta users saving videos successfully
- ✅ <3 minute processing time per video

---

## Phase 2: Frontend & Search Experience (2 weeks)

**Goal:** Build beautiful web app where users can search and manage their video library

### Week 3: Web App Frontend

#### Day 11-13: Video Library UI
**Tasks:**
- [ ] Next.js setup with Tailwind
- [ ] Video grid view with thumbnails
- [ ] Filter by platform (Instagram/YouTube/LinkedIn)
- [ ] Search bar with instant results
- [ ] Video detail modal
- [ ] Delete/edit video

**Tech Stack:**
- Next.js 14 (App Router)
- Tailwind CSS
- shadcn/ui components
- React Query for data fetching

---

#### Day 14-15: Enhanced Search Interface
**Tasks:**
- [ ] Natural language search ("pasta with tomatoes")
- [ ] Filter by date, duration, author
- [ ] Save search queries
- [ ] Search history
- [ ] "Find similar" feature

---

### Week 4: Chat & Interactions

#### Day 16-17: Chat Interface Improvements
**Tasks:**
- [ ] Better chat UI (like ChatGPT)
- [ ] Video previews in chat responses
- [ ] Click timestamp → play video at that moment
- [ ] Multi-video queries ("compare these 3 workouts")
- [ ] Export chat as markdown

---

#### Day 18-20: Organization Features
**Tasks:**
- [ ] Collections/Playlists
- [ ] Manual tags
- [ ] Auto-categorization (AI suggests tags)
- [ ] Favorites
- [ ] Recently viewed

---

## Phase 3: Vector DB Migration & Optimization (1 week)

### Week 5: Performance, Storage & Architecture Overhaul

**Goal:** Reduce 70 MB → 7 MB per video, 3.4 min → 1 min processing time

This is the **most critical phase** for scalability. Without these optimizations, the product cannot scale past 1,000 users without prohibitive costs.

---

#### Day 21-22: Migrate to Vector Database

**Current Problem:**
- Pixeltable stores everything in embedded PostgreSQL (48 MB overhead)
- Frame images stored unnecessarily (5.8 MB) when we only need embeddings (410 KB)
- Re-encoded videos kept after processing (8.7 MB waste)
- Not designed for multi-tenant production workloads

**Solution: PostgreSQL + Pinecone/Qdrant**

**Tasks:**
- [ ] Choose Vector DB (Pinecone vs Qdrant comparison)
- [ ] Set up Pinecone/Qdrant instance
- [ ] Create new video processing pipeline (without Pixeltable)
- [ ] Migrate existing videos to new architecture
- [ ] Update search endpoints to use Vector DB

---

**Vector DB Comparison:**

| Feature | Pinecone | Qdrant | Weaviate |
|---------|----------|--------|----------|
| **Pricing** | $70/month (1M vectors) | Free (self-hosted) | Free (self-hosted) |
| **Setup** | Cloud, instant | Docker container | Docker container |
| **Performance** | Excellent | Excellent | Good |
| **Recommendation** | **MVP (fastest)** | **Production (cost)** | Alternative |

**Decision: Start with Pinecone (MVP), migrate to self-hosted Qdrant later**

---

**New Video Processing Pipeline:**

```python
# recollect-mcp/src/recollect_mcp/video/optimized_processor.py
import cv2
import numpy as np
from typing import Dict, List
import openai
from pinecone import Pinecone
from concurrent.futures import ThreadPoolExecutor, as_completed

class OptimizedVideoProcessor:
    """
    New video processor that:
    1. Reduces frames: 45 → 20
    2. Doesn't store frame images
    3. Batches OpenAI API calls
    4. Processes frames + audio in parallel
    5. Stores only embeddings in Pinecone
    """

    def __init__(self, pinecone_api_key: str, pinecone_index: str):
        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index = self.pc.Index(pinecone_index)
        self.openai_client = openai.Client()

    def process_video(self, video_path: str, video_id: str) -> Dict:
        """Process video and store embeddings in Pinecone"""

        # Parallel processing: frames + audio simultaneously
        with ThreadPoolExecutor(max_workers=2) as executor:
            frame_future = executor.submit(self._process_frames, video_path, video_id)
            audio_future = executor.submit(self._process_audio, video_path, video_id)

            frame_results = frame_future.result()
            audio_results = audio_future.result()

        return {
            "video_id": video_id,
            "frames_processed": len(frame_results),
            "audio_chunks_processed": len(audio_results),
            "total_embeddings": len(frame_results) + len(audio_results)
        }

    def _process_frames(self, video_path: str, video_id: str) -> List[Dict]:
        """
        Extract frames and generate embeddings
        OPTIMIZATION: Only 20 frames instead of 45
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        # OPTIMIZATION: 20 frames instead of 45
        NUM_FRAMES = 20
        frame_interval = duration / NUM_FRAMES

        frames_data = []
        frame_images = []  # For batching captions

        for i in range(NUM_FRAMES):
            timestamp = i * frame_interval
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ret, frame = cap.read()

            if ret:
                # Resize frame to 224x224 for CLIP
                frame_resized = cv2.resize(frame, (224, 224))
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)

                frames_data.append({
                    "timestamp": timestamp,
                    "frame": frame_rgb
                })
                frame_images.append(frame_rgb)

        cap.release()

        # OPTIMIZATION: Batch generate captions (1 API call instead of 20)
        captions = self._batch_generate_captions(frame_images)

        # OPTIMIZATION: Batch generate embeddings (1 API call instead of 20)
        caption_texts = [c["caption"] for c in captions]
        caption_embeddings = self._batch_embed_text(caption_texts)

        # Generate CLIP embeddings for frames
        clip_embeddings = self._batch_clip_embeddings(frame_images)

        # Store in Pinecone (NO FRAME IMAGES STORED)
        vectors_to_upsert = []
        for i, frame_data in enumerate(frames_data):
            # Frame visual embedding
            vectors_to_upsert.append({
                "id": f"{video_id}_frame_{i}_visual",
                "values": clip_embeddings[i].tolist(),
                "metadata": {
                    "video_id": video_id,
                    "type": "frame_visual",
                    "timestamp": frame_data["timestamp"]
                }
            })

            # Frame caption embedding
            vectors_to_upsert.append({
                "id": f"{video_id}_frame_{i}_caption",
                "values": caption_embeddings[i],
                "metadata": {
                    "video_id": video_id,
                    "type": "frame_caption",
                    "timestamp": frame_data["timestamp"],
                    "caption": captions[i]["caption"]
                }
            })

        # Batch upsert to Pinecone
        self.index.upsert(vectors=vectors_to_upsert, namespace="frames")

        return frames_data

    def _batch_generate_captions(self, frames: List[np.ndarray]) -> List[Dict]:
        """
        OPTIMIZATION: Batch generate captions for all frames in ONE API call

        Before: 20 API calls (20 × 3 seconds = 60 seconds)
        After: 1 API call (5 seconds)
        Savings: 55 seconds
        """
        # Encode frames as base64
        import base64
        from io import BytesIO
        from PIL import Image

        encoded_frames = []
        for frame in frames:
            pil_img = Image.fromarray(frame)
            buffer = BytesIO()
            pil_img.save(buffer, format="JPEG")
            b64_img = base64.b64encode(buffer.getvalue()).decode()
            encoded_frames.append(b64_img)

        # Single API call with multiple images
        # Note: GPT-4o can handle multiple images in one request
        captions = []

        # Process in batches of 5 to avoid token limits
        for i in range(0, len(encoded_frames), 5):
            batch = encoded_frames[i:i+5]

            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Generate a brief caption for each image."},
                    *[{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}}
                      for img in batch]
                ]
            }]

            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=500
            )

            # Parse captions from response
            batch_captions = response.choices[0].message.content.split("\n")
            captions.extend([{"caption": c.strip()} for c in batch_captions if c.strip()])

        return captions[:len(frames)]  # Ensure we return exactly the right number

    def _batch_embed_text(self, texts: List[str]) -> List[List[float]]:
        """
        OPTIMIZATION: Batch embed text in ONE API call

        Before: 20 API calls
        After: 1 API call
        Savings: ~15 seconds
        """
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=texts  # Can embed up to 2048 texts in one call
        )

        return [item.embedding for item in response.data]

    def _batch_clip_embeddings(self, frames: List[np.ndarray]) -> np.ndarray:
        """Generate CLIP embeddings for frames"""
        from transformers import CLIPProcessor, CLIPModel

        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        # Process all frames at once (batch processing)
        inputs = processor(images=frames, return_tensors="pt", padding=True)
        embeddings = model.get_image_features(**inputs)

        return embeddings.detach().numpy()

    def _process_audio(self, video_path: str, video_id: str) -> List[Dict]:
        """
        Extract audio, transcribe, and generate embeddings
        RUNS IN PARALLEL with frame processing
        """
        import subprocess
        import tempfile

        # Extract audio from video
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
            subprocess.run([
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "mp3",
                audio_file.name
            ], check=True, capture_output=True)

            # Transcribe with Whisper
            transcription = self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=open(audio_file.name, "rb"),
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

        # Extract text chunks with timestamps
        chunks = []
        chunk_texts = []

        for segment in transcription.segments:
            chunks.append({
                "text": segment.text,
                "start_time": segment.start,
                "end_time": segment.end
            })
            chunk_texts.append(segment.text)

        # OPTIMIZATION: Batch embed all audio chunks in ONE API call
        embeddings = self._batch_embed_text(chunk_texts)

        # Store in Pinecone
        vectors_to_upsert = []
        for i, chunk in enumerate(chunks):
            vectors_to_upsert.append({
                "id": f"{video_id}_audio_{i}",
                "values": embeddings[i],
                "metadata": {
                    "video_id": video_id,
                    "type": "audio_transcript",
                    "start_time": chunk["start_time"],
                    "end_time": chunk["end_time"],
                    "text": chunk["text"]
                }
            })

        self.index.upsert(vectors=vectors_to_upsert, namespace="audio")

        return chunks


class VideoSearchEngine:
    """Search videos using Pinecone instead of Pixeltable"""

    def __init__(self, pinecone_api_key: str, pinecone_index: str):
        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index = self.pc.Index(pinecone_index)
        self.openai_client = openai.Client()

    def search_by_text(self, query: str, video_id: str, top_k: int = 5) -> List[Dict]:
        """Search video by text query"""
        # Embed query
        embedding = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        ).data[0].embedding

        # Search Pinecone
        results = self.index.query(
            vector=embedding,
            filter={"video_id": video_id},
            top_k=top_k,
            include_metadata=True,
            namespace="audio"  # Can search "frames" or "audio"
        )

        return [
            {
                "timestamp": match.metadata["start_time"],
                "text": match.metadata["text"],
                "similarity": match.score
            }
            for match in results.matches
        ]
```

---

**Pinecone Setup:**

```python
# recollect-mcp/src/recollect_mcp/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... existing settings

    # Vector DB
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "recollect-videos"
    PINECONE_ENVIRONMENT: str = "us-east-1-aws"

    class Config:
        env_file = ".env"
```

```python
# Create Pinecone index (one-time setup)
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-api-key")

# Create index for CLIP embeddings (512 dimensions)
pc.create_index(
    name="recollect-videos",
    dimension=1536,  # OpenAI text-embedding-3-small
    metric="cosine",
    spec=ServerlessSpec(
        cloud="aws",
        region="us-east-1"
    )
)
```

---

#### Day 23: Processing Optimizations

**Tasks:**
- [ ] Reduce frame count: 45 → 20 frames ✅ (implemented above)
- [ ] Batch API calls: caption generation, embeddings ✅ (implemented above)
- [ ] Parallel processing: frames + audio ✅ (implemented above)
- [ ] Delete re-encoded video after processing
- [ ] Remove Pixeltable dependency

**Additional Optimizations:**

```python
# Delete re-encoded video after processing
import os

def cleanup_after_processing(video_path: str, keep_original: bool = True):
    """
    OPTIMIZATION: Delete re-encoded video (8.7 MB savings)

    Pixeltable re-encodes videos for consistent format.
    We don't need this - just process the original and delete it.
    """
    if not keep_original:
        os.remove(video_path)
        logger.info(f"Deleted processed video: {video_path}")
```

---

**Expected Results After Optimization:**

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Storage per video** | 70 MB | 7 MB | **10x reduction** |
| **Processing time** | 3.4 min | 1 min | **3.4x faster** |
| **API calls** | 58 calls | 8 calls | **7x fewer** |
| **Cost per video** | $0.15 | $0.05 | **3x cheaper** |
| **Capacity** | 70 videos/hr | 240 videos/hr | **3.4x more** |

**Storage Breakdown:**

```
Before (Pixeltable):
├─ Embedded PostgreSQL: 48 MB
├─ Frame images: 5.8 MB (45 frames × ~130 KB)
├─ Re-encoded video: 8.7 MB
├─ Embeddings: 0.41 MB
└─ Total: 70 MB

After (Vector DB):
├─ PostgreSQL metadata: 0.1 MB (video info, timestamps)
├─ Pinecone embeddings: 0.31 MB
│  ├─ Frame visual: 20 × 512 dim × 4 bytes = 40 KB
│  ├─ Frame captions: 20 × 1536 dim × 4 bytes = 120 KB
│  └─ Audio transcripts: 13 × 1536 dim × 4 bytes = 80 KB
├─ Original video (S3): ~5 MB (kept for playback)
└─ Total: 7 MB (90% reduction)
```

**Processing Time Breakdown:**

```
Before:
├─ Video re-encoding: 30 sec
├─ Frame extraction (45 frames): 20 sec
├─ Caption generation (45 API calls): 60 sec
├─ Text embeddings (45 API calls): 30 sec
├─ Audio transcription: 40 sec
├─ Audio embeddings (13 API calls): 10 sec
└─ Total: 3.4 min (204 seconds)

After:
├─ Frame extraction (20 frames): 10 sec
├─ Caption generation (4 batch calls): 10 sec
├─ Text embeddings (1 batch call): 3 sec
├─ CLIP embeddings (batch): 5 sec
├─ Audio transcription: 25 sec (parallel)
├─ Audio embeddings (1 batch call): 2 sec
└─ Total: 1 min (60 seconds) - PARALLEL PROCESSING
```

---

#### Day 24-25: Testing & Migration

**Tasks:**
- [ ] Test new pipeline with 10 videos
- [ ] Compare search quality: Pixeltable vs Pinecone
- [ ] Migrate existing videos to Pinecone
- [ ] Update all API endpoints
- [ ] Load testing: 100 concurrent video uploads
- [ ] Beta test with 20 users

**Migration Script:**

```python
# scripts/migrate_to_pinecone.py
from recollect_mcp.video.optimized_processor import OptimizedVideoProcessor
from recollect_mcp.video.ingestion.registry import get_registry
import logging

logger = logging.getLogger(__name__)

def migrate_all_videos():
    """Migrate all existing videos from Pixeltable to Pinecone"""
    registry = get_registry()
    processor = OptimizedVideoProcessor(
        pinecone_api_key=settings.PINECONE_API_KEY,
        pinecone_index=settings.PINECONE_INDEX_NAME
    )

    total_videos = len(registry)
    logger.info(f"Starting migration of {total_videos} videos")

    for i, (video_name, metadata) in enumerate(registry.items(), 1):
        try:
            logger.info(f"[{i}/{total_videos}] Migrating {video_name}")

            # Re-process video with new pipeline
            result = processor.process_video(
                video_path=metadata.video_path,
                video_id=video_name
            )

            logger.info(f"✅ Migrated {video_name}: {result}")

        except Exception as e:
            logger.error(f"❌ Failed to migrate {video_name}: {e}")

    logger.info("Migration complete!")

if __name__ == "__main__":
    migrate_all_videos()
```

---

**Phase 3 Success Metrics:**
- ✅ Storage reduced: 70 MB → 7 MB per video
- ✅ Processing time: 3.4 min → 1 min per video
- ✅ Search quality maintained (>95% same results as Pixeltable)
- ✅ All existing videos migrated successfully
- ✅ 100 concurrent uploads handled without errors
- ✅ API response time: <500ms for search queries
- ✅ Beta users report no quality degradation

---

## Phase 4: Launch Preparation (1 week)

### Week 6: Pre-Launch

#### Day 26-27: Documentation & Marketing
**Tasks:**
- [ ] Landing page
- [ ] Demo video (2 minutes)
- [ ] User onboarding flow
- [ ] Help documentation
- [ ] Terms of Service
- [ ] Privacy Policy

---

#### Day 28: Soft Launch
**Tasks:**
- [ ] Deploy to production (Railway/Render)
- [ ] Post on Reddit (r/productivity, r/organization)
- [ ] Post on Twitter/X
- [ ] Product Hunt launch prep
- [ ] Collect first 100 users

---

#### Day 29-30: Iterate Based on Feedback
**Tasks:**
- [ ] Monitor errors (Sentry)
- [ ] Fix bugs
- [ ] Improve UX based on user feedback
- [ ] Add most-requested features

---

## 🎯 Success Metrics

### Phase 1 (Video Save Flow)
- [ ] Bookmarklet works on Instagram/YouTube/LinkedIn
- [ ] 10 beta users each save 10+ videos
- [ ] <3 minute processing time per video
- [ ] <5% error rate on downloads

### Phase 2 (Search Experience)
- [ ] Search returns relevant results in <500ms
- [ ] Users find what they're looking for 80%+ of the time
- [ ] 50+ beta users actively using the app
- [ ] Average 20+ videos saved per user

### Phase 3 (Vector DB Migration & Optimization)
- [ ] **Storage reduced:** 70 MB → 7 MB per video (10x reduction)
- [ ] **Processing time:** 3.4 min → 1 min per video (3.4x faster)
- [ ] **API cost reduction:** $0.15 → $0.05 per video (3x cheaper)
- [ ] **Capacity increase:** 70 videos/hour → 240 videos/hour (3.4x more)
- [ ] **Vector DB migration:** All videos migrated from Pixeltable to Pinecone
- [ ] **Search quality maintained:** >95% same results as Pixeltable
- [ ] **100 concurrent uploads** handled without errors
- [ ] **User satisfaction:** >4.5/5 rating, <2% error rate

### Phase 4 (Launch)
- [ ] 100+ signups in first week
- [ ] 50+ active users
- [ ] 1,000+ videos processed
- [ ] 3-5 user testimonials

---

## 💰 Monetization (Future)

### Free Tier
- 50 videos
- Basic search
- 1 collection

### Pro Tier ($5/month)
- Unlimited videos
- Advanced search
- Unlimited collections
- Priority processing
- Export features

### Target: 100 paying users = $500 MRR by Month 3

---

## 🚨 Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| Instagram blocks downloads | Rate limiting, user authentication, manual upload fallback |
| Processing costs too high | Optimize frame count, use cheaper models, usage limits |
| Users don't find value | Talk to users weekly, iterate quickly |
| Storage costs grow | Compression, retention policies, paid tiers |
| Chrome extension rejected | Have bookmarklet as fallback, appeal rejection |

---

## 📊 Cost Estimation

### MVP (Months 1-3) - Post-Optimization
- **Hosting:** Railway/Render ~$50/month
- **Redis:** Upstash free tier → $0
- **PostgreSQL:** Supabase free tier → $0
- **Pinecone:** Starter plan (100K vectors) → $70/month
- **OpenAI API:** ~$50-100/month (100 videos × $0.05/video after optimization)
- **Total:** $120-170/month

**Before optimization:** $150-250/month
**Savings:** ~$30-80/month (30% reduction)

### At 500 Users (Month 6) - Post-Optimization
- **Hosting:** ~$150/month (optimized processing = less compute)
- **Database:** ~$25/month (10x less storage)
- **Pinecone:** ~$140/month (2M vectors = 500 users × 100 videos × 40 embeddings/video)
- **OpenAI API:** ~$250/month (5,000 videos × $0.05/video)
- **Storage (S3):** ~$175/month (5,000 videos × 5 MB × $0.007/GB)
- **Total:** $740/month
- **Revenue (10% paying):** $250/month
- **Net:** -$490/month

**Before optimization:**
- Total: ~$1,200/month (70 MB/video storage + higher API costs)
- Net: -$950/month
- **Savings: $460/month (38% cost reduction)**

### At 5,000 Users (Month 12) - Post-Optimization
- **Hosting:** ~$500/month
- **Database:** ~$100/month
- **Pinecone:** ~$500/month (20M vectors)
- **OpenAI API:** ~$2,500/month (50,000 videos)
- **Storage (S3):** ~$1,750/month (50,000 videos × 5 MB)
- **Total:** $5,350/month
- **Revenue (20% paying):** $5,000/month
- **Net:** -$350/month (close to breakeven!)

**Before optimization:**
- Total: ~$12,000/month
- Net: -$7,000/month
- **Savings: $6,650/month (55% cost reduction)**

**Key Insight:** Optimization makes the difference between $7K/month loss and near-breakeven at 5K users.

---

## 🔄 Weekly Milestones

### Week 1
- ✅ Video download service working
- ✅ API endpoint for saving videos
- ✅ Database schema deployed
- ✅ 5 test videos processed successfully

### Week 2
- ✅ Bookmarklet MVP live
- ✅ Chrome extension submitted
- ✅ 10 beta users testing
- ✅ First real user saves a video

### Week 3
- ✅ Web app deployed
- ✅ Video library UI complete
- ✅ Search working
- ✅ 20+ beta users

### Week 4
- ✅ Chat interface improved
- ✅ Collections working
- ✅ 50+ beta users
- ✅ 500+ videos processed

### Week 5
- ✅ Processing optimized (<1 min)
- ✅ Storage optimized (<10 MB/video)
- ✅ Bug fixes complete
- ✅ Ready for launch

### Week 6
- ✅ Landing page live
- ✅ Demo video published
- ✅ Soft launch (Reddit, Twitter)
- ✅ 100+ signups
- ✅ Collect feedback for v2

---

## 🎉 Next Steps

### This Week (Week 1)
1. [ ] Add yt-dlp to requirements
2. [ ] Implement VideoDownloader service
3. [ ] Test Instagram Reel download
4. [ ] Test YouTube Short download
5. [ ] Create Celery task for download + process
6. [ ] Deploy database schema
7. [ ] Test end-to-end flow

### Next Week (Week 2)
1. [ ] Build bookmarklet
2. [ ] Start Chrome extension
3. [ ] Get 5-10 beta users
4. [ ] Collect feedback
5. [ ] Fix bugs

---

## 📚 Resources

### User Research Questions
Before building features, ask users:
1. How many videos have you saved? (target: 100+)
2. How often do you try to find old videos? (weekly = good signal)
3. How long does it take to find them? (most say: "I give up")
4. What would you pay for instant search? ($5/month = good signal)
5. Instagram/YouTube/both? (both = bigger market)

### Validation Metrics
- **Problem exists:** 10+ people say "I have this problem"
- **Willing to try:** 5+ people say "I'd use this"
- **Willing to pay:** 3+ people say "I'd pay $5/month"

If you hit these numbers → BUILD IT
If you don't → PIVOT

---

**Status:** Phase 1 in progress, Week 1 starting NOW 🚀
**Next Review:** End of Week 1 (5 days from now)

---

## 🔥 Critical Architecture Changes Summary

### From Educational Project → Production Consumer App

**What Changed:**
1. **Target Users:** Developers learning video processing → Consumers saving 50+ reels/shorts/month
2. **Product:** Backend video processor → Full consumer app with browser extension
3. **Architecture:** Pixeltable monolith → PostgreSQL + Pinecone + S3 microservices
4. **Storage:** 70 MB/video → 7 MB/video (10x reduction)
5. **Processing:** 3.4 min/video → 1 min/video (3.4x faster)
6. **Cost:** $0.15/video → $0.05/video (3x cheaper)

---

### Key Technical Decisions

| Component | Before (Pixeltable) | After (Vector DB) | Reason |
|-----------|---------------------|-------------------|--------|
| **Storage** | Embedded PostgreSQL | External PostgreSQL | Multi-tenant, production-ready |
| **Embeddings** | Pixeltable tables | Pinecone/Qdrant | Scalable, cost-effective |
| **Frame Count** | 45 frames/video | 20 frames/video | Sufficient coverage, 2x faster |
| **API Calls** | 58 individual calls | 8 batch calls | 7x fewer calls, 40s faster |
| **Frame Storage** | Store images (5.8 MB) | Store embeddings only (40 KB) | 145x reduction |
| **Video Storage** | Re-encoded copy (8.7 MB) | Original only (5 MB) | 1.7x smaller |
| **Processing** | Sequential | Parallel (frames + audio) | 2x faster |

---

### Why This Matters for Scalability

**Before Optimization:**
- 100K users × 100 videos = 700 TB storage
- Storage cost: ~$16,000/month
- Processing capacity: 70 videos/hour
- **Result:** Cannot scale past 1,000 users without prohibitive costs

**After Optimization:**
- 100K users × 100 videos = 70 TB storage
- Storage cost: ~$1,600/month
- Processing capacity: 240 videos/hour
- **Result:** Can scale to 10K+ users profitably

**The optimization in Phase 3 is not optional—it's the difference between a hobby project and a real business.**

---

### Migration Roadmap

```
Phase 0 (✅ Done):
└─ Built functional video processing pipeline with Pixeltable

Phase 1 (Week 1-2):
└─ Add video download service (yt-dlp)
└─ Build bookmarklet + Chrome extension
└─ Still using Pixeltable (temporary)

Phase 2 (Week 3-4):
└─ Build Next.js frontend
└─ Video library + search UI
└─ Still using Pixeltable (temporary)

Phase 3 (Week 5) - CRITICAL:
└─ Migrate from Pixeltable to PostgreSQL + Pinecone
└─ Implement all optimizations (10x storage, 3x speed)
└─ This migration MUST happen before launch

Phase 4 (Week 6):
└─ Launch to first 100 users
└─ With optimized architecture ✅
```

---

### What We Keep from Pixeltable Work

Even though we're migrating away from Pixeltable, the work wasn't wasted:

✅ **Video processing logic** - Frame extraction, audio transcription (reusable)
✅ **Embedding generation** - CLIP + OpenAI embeddings (same approach)
✅ **Search algorithms** - Similarity search concepts (transferred to Pinecone)
✅ **Docker infrastructure** - Celery, Redis, PostgreSQL (kept)
✅ **API design** - Endpoints and data models (mostly unchanged)

**We're not starting over—we're upgrading the storage layer.**

---

### Next Actions

**This Week:**
1. [ ] Start Phase 1: VideoDownloader service (Day 1-2)
2. [ ] Database schema for video metadata (Day 5)
3. [ ] Bookmarklet MVP (Day 6-7)

**Week 5 (Most Critical):**
1. [ ] Set up Pinecone account
2. [ ] Implement OptimizedVideoProcessor
3. [ ] Migrate all existing videos
4. [ ] Verify 10x storage reduction
5. [ ] Verify 3x processing speedup

**Success = Launching Phase 4 with optimized architecture, not Pixeltable.**
