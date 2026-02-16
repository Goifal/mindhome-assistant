"""
Memory Manager - Gedaechtnis des MindHome Assistants.
Working Memory (Redis) + Episodic Memory (ChromaDB).
"""

import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

from .config import settings

logger = logging.getLogger(__name__)


class MemoryManager:
    """Verwaltet das Kurz- und Langzeitgedaechtnis des Assistenten."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.chroma_collection = None
        self._chroma_client = None

    async def initialize(self):
        """Initialisiert Redis und ChromaDB Verbindungen."""
        # Redis (Working Memory)
        try:
            self.redis = redis.from_url(
                settings.redis_url, decode_responses=True
            )
            await self.redis.ping()
            logger.info("Redis verbunden")
        except Exception as e:
            logger.warning("Redis nicht verfuegbar: %s", e)
            self.redis = None

        # ChromaDB (Episodic Memory)
        try:
            import chromadb

            self._chroma_client = chromadb.HttpClient(
                host=settings.chroma_url.replace("http://", "").split(":")[0],
                port=int(settings.chroma_url.split(":")[-1]),
            )
            self.chroma_collection = self._chroma_client.get_or_create_collection(
                name="mha_conversations",
                metadata={"description": "MindHome Assistant Gespraeche und Erinnerungen"},
            )
            logger.info("ChromaDB verbunden, Collection: mha_conversations")
        except Exception as e:
            logger.warning("ChromaDB nicht verfuegbar: %s", e)
            self.chroma_collection = None

    # ----- Health Checks -----

    async def check_redis_health(self) -> bool:
        """Prueft ob Redis erreichbar ist."""
        if not self.redis:
            return False
        try:
            return await self.redis.ping()
        except Exception:
            return False

    def check_chroma_health(self) -> bool:
        """Prueft ob ChromaDB erreichbar ist."""
        if not self._chroma_client:
            return False
        try:
            self._chroma_client.heartbeat()
            return True
        except Exception:
            return False

    # ----- Working Memory (Redis) -----

    async def add_conversation(self, role: str, content: str):
        """Speichert eine Nachricht im Working Memory."""
        if not self.redis:
            return

        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        await self.redis.lpush("mha:conversations", json.dumps(entry))
        # Nur die letzten 50 Nachrichten behalten
        await self.redis.ltrim("mha:conversations", 0, 49)

    async def get_recent_conversations(self, limit: int = 5) -> list[dict]:
        """Holt die letzten Gespraeche aus dem Working Memory."""
        if not self.redis:
            return []

        entries = await self.redis.lrange("mha:conversations", 0, limit - 1)
        return [json.loads(e) for e in entries][::-1]  # Aelteste zuerst

    async def set_context(self, key: str, value: str, ttl: int = 3600):
        """Speichert einen Kontext-Wert mit TTL."""
        if not self.redis:
            return
        await self.redis.setex(f"mha:context:{key}", ttl, value)

    async def get_context(self, key: str) -> Optional[str]:
        """Holt einen Kontext-Wert."""
        if not self.redis:
            return None
        return await self.redis.get(f"mha:context:{key}")

    # ----- Episodic Memory (ChromaDB) -----

    async def store_episode(self, conversation: str, metadata: Optional[dict] = None):
        """Speichert ein Gespraech im Langzeitgedaechtnis."""
        if not self.chroma_collection:
            return

        try:
            doc_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            meta = metadata or {}
            meta["timestamp"] = datetime.now().isoformat()
            meta["type"] = "conversation"

            self.chroma_collection.add(
                documents=[conversation],
                metadatas=[meta],
                ids=[doc_id],
            )
            logger.debug("Episode gespeichert: %s", doc_id)
        except Exception as e:
            logger.error("Fehler beim Speichern der Episode: %s", e)

    async def search_memories(self, query: str, limit: int = 3) -> list[dict]:
        """Sucht relevante Erinnerungen per Vektor-Suche."""
        if not self.chroma_collection:
            return []

        try:
            results = self.chroma_collection.query(
                query_texts=[query],
                n_results=limit,
            )

            memories = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                    memories.append({
                        "content": doc,
                        "timestamp": meta.get("timestamp", ""),
                        "relevance": results["distances"][0][i]
                        if results.get("distances")
                        else 0,
                    })
            return memories
        except Exception as e:
            logger.error("Fehler bei Memory-Suche: %s", e)
            return []

    # ----- Proaktive Meldungen -----

    async def get_last_notification_time(self, event_type: str) -> Optional[str]:
        """Wann wurde dieser Event-Typ zuletzt gemeldet?"""
        if not self.redis:
            return None
        return await self.redis.get(f"mha:notify:{event_type}")

    async def set_last_notification_time(self, event_type: str):
        """Markiert wann dieser Event-Typ gemeldet wurde."""
        if not self.redis:
            return
        await self.redis.setex(
            f"mha:notify:{event_type}",
            3600,  # 1 Stunde TTL
            datetime.now().isoformat(),
        )

    # ----- Feedback Scores -----

    async def get_feedback_score(self, event_type: str) -> float:
        """Holt den Feedback-Score fuer einen Event-Typ."""
        if not self.redis:
            return 0.5
        score = await self.redis.get(f"mha:feedback:{event_type}")
        return float(score) if score else 0.5

    async def update_feedback_score(self, event_type: str, delta: float):
        """Aktualisiert den Feedback-Score."""
        if not self.redis:
            return
        current = await self.get_feedback_score(event_type)
        new_score = max(0.0, min(1.0, current + delta))
        await self.redis.set(f"mha:feedback:{event_type}", str(new_score))

    async def close(self):
        """Schliesst Verbindungen."""
        if self.redis:
            await self.redis.close()
