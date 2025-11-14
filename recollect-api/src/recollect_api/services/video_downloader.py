"""Video downloader service for Instagram and YouTube"""
import re
from pathlib import Path
from typing import Dict, Literal
from uuid import uuid4

import yt_dlp
from loguru import logger


class VideoDownloader:
    """Download videos from Instagram and YouTube"""

    def __init__(self, download_dir: str = "shared_media"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)

    def detect_source(self, url: str) -> Literal["instagram", "youtube", "linkedin", "tiktok", "unknown"]:
        """
        Detect the source platform from URL

        Args:
            url: Video URL

        Returns:
            Source platform: 'instagram', 'youtube', 'linkedin', 'tiktok', or 'unknown'
        """
        if "instagram.com" in url or "instagr.am" in url:
            return "instagram"
        elif "youtube.com" in url or "youtu.be" in url:
            return "youtube"
        elif "linkedin.com" in url:
            return "linkedin"
        elif "tiktok.com" in url:
            return "tiktok"
        else:
            return "unknown"

    def extract_video_id(self, url: str, source: str) -> str:
        """
        Extract video ID from URL

        Args:
            url: Video URL
            source: Video source platform

        Returns:
            Video ID extracted from URL
        """
        if source == "instagram":
            # Instagram Reel URL pattern: https://www.instagram.com/reel/VIDEO_ID/
            # Also handle posts: https://www.instagram.com/p/POST_ID/
            match = re.search(r"/(reel|p)/([A-Za-z0-9_-]+)", url)
            if match:
                return match.group(2)
        elif source == "youtube":
            # YouTube Shorts URL patterns:
            # https://www.youtube.com/shorts/VIDEO_ID
            # https://youtu.be/VIDEO_ID
            # https://www.youtube.com/watch?v=VIDEO_ID
            if "shorts/" in url:
                match = re.search(r"/shorts/([A-Za-z0-9_-]+)", url)
            elif "youtu.be/" in url:
                match = re.search(r"youtu\.be/([A-Za-z0-9_-]+)", url)
            else:
                match = re.search(r"[?&]v=([A-Za-z0-9_-]+)", url)
            if match:
                return match.group(1)
        elif source == "linkedin":
            # LinkedIn post URL patterns:
            # https://www.linkedin.com/posts/username_activity-1234567890-abcd
            # https://www.linkedin.com/feed/update/urn:li:activity:1234567890
            match = re.search(r"activity[-:](\d+)", url)
            if match:
                return match.group(1)
        elif source == "tiktok":
            # TikTok video URL pattern:
            # https://www.tiktok.com/@username/video/1234567890
            # https://vm.tiktok.com/SHORT_CODE/
            if "/video/" in url:
                match = re.search(r"/video/(\d+)", url)
                if match:
                    return match.group(1)
            elif "vm.tiktok.com" in url:
                match = re.search(r"vm\.tiktok\.com/([A-Za-z0-9]+)", url)
                if match:
                    return match.group(1)

        # Fallback to UUID if extraction fails
        return str(uuid4())[:8]

    def download(self, url: str) -> Dict:
        """
        Download video from URL

        Args:
            url: Video URL to download

        Returns:
            Dict containing download result with file path, metadata, and status
        """
        source = self.detect_source(url)
        if source == "unknown":
            raise ValueError(f"Unsupported URL: {url}")

        video_id = self.extract_video_id(url, source)
        logger.info(f"Downloading {source} video: {video_id} from {url}")

        # Configure yt-dlp options
        ydl_opts = {
            "format": "best[ext=mp4]/best",  # Prefer MP4, fallback to best available
            "outtmpl": str(self.download_dir / f"{source}_{video_id}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "writethumbnail": True,  # Extract thumbnail
            "writesubtitles": True,  # Extract subtitles if available
            "writeautomaticsub": True,  # Extract auto-generated subtitles
        }

        # Platform-specific options
        if source == "instagram":
            ydl_opts["cookiefile"] = None  # Add cookie file path if needed for auth
        elif source == "linkedin":
            # LinkedIn might require authentication for some posts
            ydl_opts["cookiefile"] = None
        elif source == "tiktok":
            # TikTok specific options
            ydl_opts["http_headers"] = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract video info
                info = ydl.extract_info(url, download=True)

                if not info:
                    raise Exception("Failed to extract video information")

                # Get the downloaded file path
                file_path = ydl.prepare_filename(info)

                # Get thumbnail path if available
                thumbnail_path = info.get("thumbnail")
                if not thumbnail_path and "thumbnails" in info and info["thumbnails"]:
                    thumbnail_path = info["thumbnails"][-1].get("url")

                logger.info(f"Successfully downloaded video to: {file_path}")
                if thumbnail_path:
                    logger.info(f"Thumbnail available at: {thumbnail_path}")

                return {
                    "status": "success",
                    "file_path": file_path,
                    "video_id": video_id,
                    "source": source,
                    "thumbnail_url": thumbnail_path,
                    "metadata": {
                        "title": info.get("title"),
                        "author": info.get("uploader") or info.get("channel"),
                        "duration": info.get("duration"),
                        "description": info.get("description"),
                        "upload_date": info.get("upload_date"),
                        "view_count": info.get("view_count"),
                        "like_count": info.get("like_count"),
                        "webpage_url": info.get("webpage_url"),
                        "format": info.get("format"),
                        "width": info.get("width"),
                        "height": info.get("height"),
                    },
                }

        except Exception as e:
            logger.error(f"Error downloading video from {url}: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "url": url,
                "source": source,
            }
