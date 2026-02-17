"""
Semantic Memory - Langzeit-Fakten des MindHome Assistants.
Speichert extrahierte Fakten aus Gespraechen (Praeferenzen, Personen, Gewohnheiten).
Nutzt ChromaDB fuer Vektor-Suche und Redis fuer schnellen Zugriff.
"""

import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

from .config import settings

logger = logging.getLogger(__name__)

# Fakten-Kategorien
FACT_CATEGORIES = [
    "preference",   # "Max mag 21 Grad im Buero"
    "person",       # "Lisa ist die Freundin von Max"
    "habit",        # "Max steht um 7 Uhr auf"
    "health",       # "Max hat eine Haselnuss-Allergie"
    "work",         # "Max arbeitet an Projekt Aurora"
    "general",      # Sonstige Fakten
]


class SemanticFact:
    """Ein einzelner semantischer Fakt."""

    def __init__(
        self,
        content: str,
        category: str,
        person: str = "unknown",
        confidence: float = 0.8,
        source_conversation: str = "",
        fact_id: Optional[str] = None,
    ):
        self.fact_id = fact_id or f"fact_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        self.content = content
        self.category = category if category in FACT_CATEGORIES else "general"
        self.person = person
        self.confidence = confidence
        self.source_conversation = source_conversation
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.times_confirmed = 1

    def to_dict(self) -> dict:
        return {
            "fact_id": self.fact_id,
            "content": self.content,
            "category": self.category,
            "person": self.person,
            "confidence": str(self.confidence),
            "source_conversation": self.source_conversation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "times_confirmed": str(self.times_confirmed),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SemanticFact":
        fact = cls(
            content=data.get("content", ""),
            category=data.get("category", "general"),
            person=data.get("person", "unknown"),
            confidence=float(data.get("confidence", 0.8)),
            source_conversation=data.get("source_conversation", ""),
            fact_id=data.get("fact_id"),
        )
        fact.created_at = data.get("created_at", fact.created_at)
        fact.updated_at = data.get("updated_at", fact.updated_at)
        fact.times_confirmed = int(data.get("times_confirmed", 1))
        return fact


class SemanticMemory:
    """Verwaltet semantische Fakten ueber ChromaDB + Redis."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.chroma_collection = None
        self._chroma_client = None

    async def initialize(self, redis_client: Optional[redis.Redis] = None):
        """Initialisiert die Verbindungen."""
        # Redis (schneller Zugriff auf Fakten nach Person/Kategorie)
        self.redis = redis_client

        # ChromaDB (Vektor-Suche ueber Fakten)
        try:
            import chromadb

            self._chroma_client = chromadb.HttpClient(
                host=settings.chroma_url.replace("http://", "").split(":")[0],
                port=int(settings.chroma_url.split(":")[-1]),
            )
            self.chroma_collection = self._chroma_client.get_or_create_collection(
                name="mha_semantic_facts",
                metadata={"description": "MindHome Assistant - Extrahierte Fakten"},
            )
            logger.info("Semantic Memory initialisiert (ChromaDB: mha_semantic_facts)")
        except Exception as e:
            logger.warning("Semantic Memory ChromaDB nicht verfuegbar: %s", e)
            self.chroma_collection = None

    async def store_fact(self, fact: SemanticFact) -> bool:
        """
        Speichert einen Fakt. Prueft vorher auf Duplikate.

        Returns:
            True wenn gespeichert, False bei Fehler
        """
        # Duplikat-Check: aehnlichen Fakt suchen
        existing = await self.find_similar_fact(fact.content, threshold=0.15)
        if existing:
            # Fakt existiert bereits -> aktualisieren
            return await self._update_existing_fact(existing, fact)

        # Neuer Fakt -> in ChromaDB speichern
        if self.chroma_collection:
            try:
                self.chroma_collection.add(
                    documents=[fact.content],
                    metadatas=[fact.to_dict()],
                    ids=[fact.fact_id],
                )
            except Exception as e:
                logger.error("Fehler beim Speichern in ChromaDB: %s", e)
                return False

        # In Redis-Index speichern (schneller Zugriff)
        if self.redis:
            try:
                # Fakt-Details als Hash
                await self.redis.hset(
                    f"mha:fact:{fact.fact_id}",
                    mapping=fact.to_dict(),
                )
                # Index nach Person
                await self.redis.sadd(
                    f"mha:facts:person:{fact.person}",
                    fact.fact_id,
                )
                # Index nach Kategorie
                await self.redis.sadd(
                    f"mha:facts:category:{fact.category}",
                    fact.fact_id,
                )
                # Index: alle Fakten
                await self.redis.sadd("mha:facts:all", fact.fact_id)
            except Exception as e:
                logger.error("Fehler beim Redis-Index: %s", e)

        logger.info(
            "Neuer Fakt gespeichert: [%s] %s (Person: %s)",
            fact.category, fact.content, fact.person,
        )
        return True

    async def _update_existing_fact(
        self, existing: dict, new_fact: SemanticFact
    ) -> bool:
        """Aktualisiert einen bestehenden Fakt (Confidence erhoehen)."""
        fact_id = existing.get("fact_id", "")
        if not fact_id:
            return False

        now = datetime.now().isoformat()
        times_confirmed = int(existing.get("times_confirmed", 1)) + 1
        new_confidence = min(1.0, float(existing.get("confidence", 0.8)) + 0.05)

        # ChromaDB aktualisieren
        if self.chroma_collection:
            try:
                updated_meta = existing.copy()
                updated_meta["updated_at"] = now
                updated_meta["times_confirmed"] = str(times_confirmed)
                updated_meta["confidence"] = str(new_confidence)
                # Wenn neuer Inhalt besser/laenger ist, aktualisieren
                new_content = new_fact.content if len(new_fact.content) > len(existing.get("content", "")) else existing.get("content", "")
                self.chroma_collection.update(
                    ids=[fact_id],
                    documents=[new_content],
                    metadatas=[updated_meta],
                )
            except Exception as e:
                logger.error("Fehler beim Update in ChromaDB: %s", e)

        # Redis aktualisieren
        if self.redis:
            try:
                await self.redis.hset(f"mha:fact:{fact_id}", "updated_at", now)
                await self.redis.hset(
                    f"mha:fact:{fact_id}", "times_confirmed", str(times_confirmed)
                )
                await self.redis.hset(
                    f"mha:fact:{fact_id}", "confidence", str(new_confidence)
                )
            except Exception as e:
                logger.error("Fehler beim Redis-Update: %s", e)

        logger.debug(
            "Fakt bestaetigt: %s (x%d, Confidence: %.2f)",
            fact_id, times_confirmed, new_confidence,
        )
        return True

    async def find_similar_fact(
        self, query: str, threshold: float = 0.15
    ) -> Optional[dict]:
        """
        Sucht nach einem aehnlichen Fakt (Duplikat-Erkennung).

        Args:
            query: Fakt-Text
            threshold: Maximale Distanz fuer Match (kleiner = aehnlicher)

        Returns:
            Existierender Fakt oder None
        """
        if not self.chroma_collection:
            return None

        try:
            results = self.chroma_collection.query(
                query_texts=[query],
                n_results=1,
            )
            if (
                results
                and results.get("documents")
                and results["documents"][0]
                and results.get("distances")
                and results["distances"][0]
            ):
                distance = results["distances"][0][0]
                if distance <= threshold:
                    meta = results["metadatas"][0][0] if results.get("metadatas") else {}
                    return meta
        except Exception as e:
            logger.error("Fehler bei Duplikat-Suche: %s", e)

        return None

    async def search_facts(
        self, query: str, limit: int = 5, person: Optional[str] = None
    ) -> list[dict]:
        """
        Sucht relevante Fakten per Vektor-Suche.

        Args:
            query: Suchtext
            limit: Maximale Ergebnisse
            person: Optional - nur Fakten dieser Person

        Returns:
            Liste von Fakten mit Relevanz
        """
        if not self.chroma_collection:
            return []

        try:
            where_filter = None
            if person:
                where_filter = {"person": person}

            results = self.chroma_collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_filter,
            )

            facts = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = (
                        results["distances"][0][i] if results.get("distances") else 1.0
                    )
                    facts.append({
                        "content": doc,
                        "category": meta.get("category", "general"),
                        "person": meta.get("person", "unknown"),
                        "confidence": float(meta.get("confidence", 0.5)),
                        "times_confirmed": int(meta.get("times_confirmed", 1)),
                        "relevance": 1.0 - min(distance, 1.0),
                    })
            return facts
        except Exception as e:
            logger.error("Fehler bei Fakten-Suche: %s", e)
            return []

    async def get_facts_by_person(self, person: str) -> list[dict]:
        """Holt alle Fakten fuer eine Person (schnell via Redis)."""
        if not self.redis:
            # Fallback auf ChromaDB
            return await self.search_facts(person, limit=20, person=person)

        try:
            fact_ids = await self.redis.smembers(f"mha:facts:person:{person}")
            facts = []
            for fact_id in fact_ids:
                data = await self.redis.hgetall(f"mha:fact:{fact_id}")
                if data:
                    facts.append({
                        "content": data.get("content", ""),
                        "category": data.get("category", "general"),
                        "person": data.get("person", person),
                        "confidence": float(data.get("confidence", 0.5)),
                        "times_confirmed": int(data.get("times_confirmed", 1)),
                    })
            # Nach Confidence sortieren
            facts.sort(key=lambda f: f["confidence"], reverse=True)
            return facts
        except Exception as e:
            logger.error("Fehler bei Person-Fakten: %s", e)
            return []

    async def get_facts_by_category(self, category: str) -> list[dict]:
        """Holt alle Fakten einer Kategorie."""
        if not self.redis:
            return await self.search_facts(category, limit=20)

        try:
            fact_ids = await self.redis.smembers(f"mha:facts:category:{category}")
            facts = []
            for fact_id in fact_ids:
                data = await self.redis.hgetall(f"mha:fact:{fact_id}")
                if data:
                    facts.append({
                        "content": data.get("content", ""),
                        "category": category,
                        "person": data.get("person", "unknown"),
                        "confidence": float(data.get("confidence", 0.5)),
                    })
            return facts
        except Exception as e:
            logger.error("Fehler bei Kategorie-Fakten: %s", e)
            return []

    async def get_all_facts(self) -> list[dict]:
        """Holt alle gespeicherten Fakten."""
        if not self.redis:
            return []

        try:
            fact_ids = await self.redis.smembers("mha:facts:all")
            facts = []
            for fact_id in fact_ids:
                data = await self.redis.hgetall(f"mha:fact:{fact_id}")
                if data:
                    facts.append({
                        "fact_id": data.get("fact_id", fact_id),
                        "content": data.get("content", ""),
                        "category": data.get("category", "general"),
                        "person": data.get("person", "unknown"),
                        "confidence": float(data.get("confidence", 0.5)),
                        "times_confirmed": int(data.get("times_confirmed", 1)),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                    })
            facts.sort(key=lambda f: f["confidence"], reverse=True)
            return facts
        except Exception as e:
            logger.error("Fehler beim Laden aller Fakten: %s", e)
            return []

    async def delete_fact(self, fact_id: str) -> bool:
        """Loescht einen Fakt."""
        # Aus ChromaDB loeschen
        if self.chroma_collection:
            try:
                self.chroma_collection.delete(ids=[fact_id])
            except Exception as e:
                logger.error("Fehler beim Loeschen aus ChromaDB: %s", e)

        # Aus Redis loeschen
        if self.redis:
            try:
                data = await self.redis.hgetall(f"mha:fact:{fact_id}")
                if data:
                    person = data.get("person", "unknown")
                    category = data.get("category", "general")
                    await self.redis.srem(f"mha:facts:person:{person}", fact_id)
                    await self.redis.srem(f"mha:facts:category:{category}", fact_id)
                    await self.redis.srem("mha:facts:all", fact_id)
                    await self.redis.delete(f"mha:fact:{fact_id}")
                    logger.info("Fakt geloescht: %s", fact_id)
                    return True
            except Exception as e:
                logger.error("Fehler beim Loeschen aus Redis: %s", e)

        return False

    async def get_stats(self) -> dict:
        """Gibt Statistiken ueber das semantische Gedaechtnis."""
        if not self.redis:
            return {"total_facts": 0, "categories": {}, "persons": []}

        try:
            total = await self.redis.scard("mha:facts:all")
            categories = {}
            for cat in FACT_CATEGORIES:
                count = await self.redis.scard(f"mha:facts:category:{cat}")
                if count > 0:
                    categories[cat] = count

            # Alle Personen mit Fakten
            persons = set()
            fact_ids = await self.redis.smembers("mha:facts:all")
            for fact_id in fact_ids:
                person = await self.redis.hget(f"mha:fact:{fact_id}", "person")
                if person:
                    persons.add(person)

            return {
                "total_facts": total,
                "categories": categories,
                "persons": list(persons),
            }
        except Exception as e:
            logger.error("Fehler bei Stats: %s", e)
            return {"total_facts": 0, "categories": {}, "persons": []}
