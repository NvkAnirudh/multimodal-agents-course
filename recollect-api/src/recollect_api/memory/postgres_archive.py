"""PostgreSQL-based archive for cold storage and video metadata"""
import asyncpg
import json
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger


class PostgresArchive:
    """Cold storage for conversation archives and video metadata"""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Initialize connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.db_url,
                min_size=5,
                max_size=20,
                command_timeout=60,
            )
            await self._create_tables()
            logger.info("PostgreSQL archive connected")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def _create_tables(self):
        """Create necessary tables if they don't exist"""
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
                    source VARCHAR(50) NOT NULL,
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

    async def archive_conversation(
        self,
        session_id: str,
        messages: List[Dict],
        user_id: Optional[str] = None,
    ):
        """Archive conversation from Redis to Postgres"""
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for msg in messages:
                    await conn.execute(
                        """
                        INSERT INTO conversations
                        (session_id, user_id, role, content, metadata, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        session_id,
                        user_id,
                        msg["role"],
                        msg["content"],
                        json.dumps(msg.get("metadata", {})),
                        datetime.fromisoformat(msg["timestamp"]),
                    )
        logger.info(f"Archived {len(messages)} messages for session {session_id}")

    async def save_video_metadata(self, video_data: Dict):
        """Save video metadata"""
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO video_metadata
                (video_id, user_id, source, original_url, title, description,
                 author, duration_seconds, file_path, thumbnail_path, tags)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (video_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    processed_at = NOW()
                """,
                video_data["video_id"],
                video_data.get("user_id"),
                video_data["source"],
                video_data.get("original_url"),
                video_data.get("title"),
                video_data.get("description"),
                video_data.get("author"),
                video_data.get("duration_seconds"),
                video_data["file_path"],
                video_data.get("thumbnail_path"),
                video_data.get("tags", []),
            )
        logger.info(f"Saved metadata for video {video_data['video_id']}")

    async def get_user_videos(
        self, user_id: str, limit: int = 50
    ) -> List[Dict]:
        """Get user's video library"""
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM video_metadata
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
            return [dict(row) for row in rows]

    async def get_conversation_history(
        self, session_id: str, limit: int = 100
    ) -> List[Dict]:
        """Get conversation history from archive"""
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content, metadata, created_at
                FROM conversations
                WHERE session_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                session_id,
                limit,
            )
            return [dict(row) for row in rows]

    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL archive closed")
