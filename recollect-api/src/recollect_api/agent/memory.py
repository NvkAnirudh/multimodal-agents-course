"""Memory adapter for backward compatibility with Redis backend"""
from datetime import datetime
from loguru import logger
from pydantic import BaseModel

from recollect_api.memory import RedisMemory
from recollect_api.config import get_settings

settings = get_settings()


class MemoryRecord(BaseModel):
    message_id: str
    role: str
    content: str
    timestamp: datetime


class Memory:
    """Memory adapter using Redis for hot storage"""

    def __init__(self, name: str):
        self.session_id = name
        self.redis_memory = RedisMemory(settings.REDIS_URL)
        logger.info(f"Initialized Redis memory for session: {name}")

    def reset_memory(self):
        """Clear conversation history"""
        logger.info(f"Resetting memory: {self.session_id}")
        self.redis_memory.reset(self.session_id)

    def insert(self, memory_record: MemoryRecord):
        """Add message to conversation"""
        self.redis_memory.add_message(
            session_id=self.session_id,
            role=memory_record.role,
            content=memory_record.content,
            metadata={"message_id": memory_record.message_id},
        )

    def get_all(self) -> list[MemoryRecord]:
        """Get all messages in session"""
        messages = self.redis_memory.get_all(self.session_id)
        return [
            MemoryRecord(
                message_id=msg["metadata"].get("message_id", ""),
                role=msg["role"],
                content=msg["content"],
                timestamp=datetime.fromisoformat(msg["timestamp"]),
            )
            for msg in messages
        ]

    def get_latest(self, n: int) -> list[MemoryRecord]:
        """Get last N messages"""
        messages = self.redis_memory.get_latest(self.session_id, n)
        return [
            MemoryRecord(
                message_id=msg["metadata"].get("message_id", ""),
                role=msg["role"],
                content=msg["content"],
                timestamp=datetime.fromisoformat(msg["timestamp"]),
            )
            for msg in messages
        ]

    def get_by_message_id(self, message_id: str) -> MemoryRecord:
        """Get specific message by ID"""
        messages = self.get_all()
        for record in messages:
            if record.message_id == message_id:
                return record
        raise ValueError(f"Message ID {message_id} not found")
