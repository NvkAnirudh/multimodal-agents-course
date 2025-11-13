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

    def detect_source(self, url: str) -> Literal["instagram", "youtube", "unknown"]:
        """
        Detect the source platform from URL

        Args:
            url: Video URL

        Returns:
            Source platform: 'instagram', 'youtube', or 'unknown'
        """
        if "instagram.com" in url or "instagr.am" in url:
            return "instagram"
        elif "youtube.com" in url or "youtu.be" in url:
            return "youtube"
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
            match = re.search(r"/reel/([A-Za-z0-9_-]+)", url)
            if match:
                return match.group(1)
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
        }

        # Instagram-specific options
        if source == "instagram":
            ydl_opts["cookiefile"] = None  # Add cookie file path if needed for auth

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract video info
                info = ydl.extract_info(url, download=True)

                if not info:
                    raise Exception("Failed to extract video information")

                # Get the downloaded file path
                file_path = ydl.prepare_filename(info)

                logger.info(f"Successfully downloaded video to: {file_path}")

                return {
                    "status": "success",
                    "file_path": file_path,
                    "video_id": video_id,
                    "source": source,
                    "metadata": {
                        "title": info.get("title"),
                        "author": info.get("uploader") or info.get("channel"),
                        "duration": info.get("duration"),
                        "description": info.get("description"),
                        "upload_date": info.get("upload_date"),
                        "view_count": info.get("view_count"),
                        "like_count": info.get("like_count"),
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
