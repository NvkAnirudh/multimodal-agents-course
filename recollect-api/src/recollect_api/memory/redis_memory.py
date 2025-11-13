"""Redis-based memory for hot storage of active conversations"""
import json
import redis
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger


class RedisMemory:
    """Hot storage for active conversations with 7-day TTL"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = 86400 * 7  # 7 days

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Add message to conversation"""
        key = f"session:{session_id}"
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        try:
            # Add to conversation
            self.client.rpush(key, json.dumps(message))

            # Keep only last 100 messages per session
            self.client.ltrim(key, -100, -1)

            # Set 7-day expiration
            self.client.expire(key, self.ttl_seconds)

            logger.debug(f"Added message to session {session_id}")
        except Exception as e:
            logger.error(f"Failed to add message to Redis: {e}")
            raise

    def get_latest(self, session_id: str, n: int = 20) -> List[Dict]:
        """Get last N messages from session"""
        key = f"session:{session_id}"
        try:
            messages = self.client.lrange(key, -n, -1)
            return [json.loads(msg) for msg in messages]
        except Exception as e:
            logger.error(f"Failed to retrieve messages from Redis: {e}")
            return []

    def get_all(self, session_id: str) -> List[Dict]:
        """Get all messages in session"""
        key = f"session:{session_id}"
        try:
            messages = self.client.lrange(key, 0, -1)
            return [json.loads(msg) for msg in messages]
        except Exception as e:
            logger.error(f"Failed to retrieve all messages from Redis: {e}")
            return []

    def reset(self, session_id: str) -> None:
        """Clear conversation"""
        key = f"session:{session_id}"
        try:
            self.client.delete(key)
            logger.info(f"Reset session {session_id}")
        except Exception as e:
            logger.error(f"Failed to reset session: {e}")
            raise

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists"""
        key = f"session:{session_id}"
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check session existence: {e}")
            return False

    def get_session_count(self) -> int:
        """Get total number of active sessions"""
        try:
            keys = self.client.keys("session:*")
            return len(keys)
        except Exception as e:
            logger.error(f"Failed to count sessions: {e}")
            return 0
