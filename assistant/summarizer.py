"""
Daily Summarizer + Langzeitgedaechtnis - Phase 7.

Laeuft naechtlich und erstellt hierarchische Zusammenfassungen:
- Tages-Zusammenfassung: ~200 Woerter, alle Gespraeche + Events
- Wochen-Zusammenfassung: aus 7 Tages-Summaries
- Monats-Zusammenfassung: aus ~4 Wochen-Summaries

Speichert in ChromaDB fuer spaetere Vektor-Suche.
So kann der Assistant Fragen wie "War der letzte Winter teuer?" beantworten.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis

from .config import settings, yaml_config
from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Summary-Typen
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"


class DailySummarizer:
    """Erstellt hierarchische Zusammenfassungen von Gespraechen und Events."""

    def __init__(self, ollama: OllamaClient, memory=None):
        self.ollama = ollama
        self.memory = memory  # MemoryManager Referenz
        self.redis: Optional[redis.Redis] = None
        self.chroma_collection = None

        # Nachtlauf-Task
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Konfiguration aus YAML
        summarizer_cfg = yaml_config.get("summarizer", {})
        self.run_hour = summarizer_cfg.get("run_hour", 3)
        self.run_minute = summarizer_cfg.get("run_minute", 0)
        self.model = summarizer_cfg.get("model", settings.model_smart)
        self.max_tokens_daily = summarizer_cfg.get("max_tokens_daily", 512)
        self.max_tokens_weekly = summarizer_cfg.get("max_tokens_weekly", 384)
        self.max_tokens_monthly = summarizer_cfg.get("max_tokens_monthly", 512)

    async def initialize(
        self,
        redis_client: Optional[redis.Redis] = None,
        chroma_collection=None,
    ):
        """Initialisiert mit Redis und ChromaDB."""
        self.redis = redis_client
        self.chroma_collection = chroma_collection
        self._running = True
        self._task = asyncio.create_task(self._nightly_loop())
        logger.info(
            "DailySummarizer initialisiert (Nachtlauf: %02d:%02d)",
            self.run_hour, self.run_minute,
        )

    async def stop(self):
        """Stoppt den Nachtlauf."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ----- Nachtlauf -----

    async def _nightly_loop(self):
        """Wartet bis zur konfigurierten Uhrzeit und erstellt Zusammenfassungen."""
        while self._running:
            try:
                now = datetime.now()
                target = now.replace(
                    hour=self.run_hour, minute=self.run_minute, second=0, microsecond=0
                )
                if target <= now:
                    target += timedelta(days=1)

                wait_seconds = (target - now).total_seconds()
                logger.info(
                    "Naechster Summary-Lauf in %.0f Stunden (%s)",
                    wait_seconds / 3600,
                    target.strftime("%Y-%m-%d %H:%M"),
                )
                await asyncio.sleep(wait_seconds)

                # Tages-Summary fuer gestern
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                await self.summarize_day(yesterday)

                # Wochen-Summary jeden Montag
                if datetime.now().weekday() == 0:
                    await self.summarize_week()

                # Monats-Summary am 1. des Monats
                if datetime.now().day == 1:
                    await self.summarize_month()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Fehler im Nachtlauf: %s", e)
                await asyncio.sleep(3600)  # 1h warten bei Fehler

    # ----- Tages-Zusammenfassung -----

    async def summarize_day(self, date: str) -> Optional[str]:
        """
        Erstellt eine Tages-Zusammenfassung.

        Args:
            date: Datum im Format "YYYY-MM-DD"

        Returns:
            Zusammenfassung als String oder None
        """
        # Pruefen ob schon existiert
        existing = await self._get_summary(date, DAILY)
        if existing:
            logger.info("Tages-Summary fuer %s existiert bereits", date)
            return existing

        # Konversationen des Tages laden
        conversations = await self._get_conversations_for_date(date)
        if not conversations:
            logger.info("Keine Konversationen fuer %s, ueberspringe", date)
            return None

        # LLM-Zusammenfassung erstellen
        prompt = self._build_daily_prompt(date, conversations)
        summary = await self._generate_summary(prompt, self.max_tokens_daily)

        if summary:
            await self._store_summary(date, DAILY, summary)
            logger.info("Tages-Summary fuer %s erstellt (%d Zeichen)", date, len(summary))

        return summary

    # ----- Wochen-Zusammenfassung -----

    async def summarize_week(self, end_date: Optional[str] = None) -> Optional[str]:
        """
        Erstellt eine Wochen-Zusammenfassung aus Tages-Summaries.

        Args:
            end_date: Letzter Tag der Woche (default: gestern)
        """
        if not end_date:
            end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=6)
        week_key = f"{start_dt.strftime('%Y-%m-%d')}_to_{end_date}"

        # Pruefen ob schon existiert
        existing = await self._get_summary(week_key, WEEKLY)
        if existing:
            logger.info("Wochen-Summary fuer %s existiert bereits", week_key)
            return existing

        # Tages-Summaries sammeln
        daily_summaries = []
        for i in range(7):
            day = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            day_summary = await self._get_summary(day, DAILY)
            if day_summary:
                daily_summaries.append(f"[{day}]: {day_summary}")

        if not daily_summaries:
            logger.info("Keine Tages-Summaries fuer Woche %s", week_key)
            return None

        prompt = self._build_weekly_prompt(week_key, daily_summaries)
        summary = await self._generate_summary(prompt, self.max_tokens_weekly)

        if summary:
            await self._store_summary(week_key, WEEKLY, summary)
            logger.info("Wochen-Summary fuer %s erstellt", week_key)

        return summary

    # ----- Monats-Zusammenfassung -----

    async def summarize_month(self, month: Optional[str] = None) -> Optional[str]:
        """
        Erstellt eine Monats-Zusammenfassung aus Wochen-Summaries.

        Args:
            month: Monat im Format "YYYY-MM" (default: letzter Monat)
        """
        if not month:
            last_month = datetime.now().replace(day=1) - timedelta(days=1)
            month = last_month.strftime("%Y-%m")

        # Pruefen ob schon existiert
        existing = await self._get_summary(month, MONTHLY)
        if existing:
            logger.info("Monats-Summary fuer %s existiert bereits", month)
            return existing

        # Wochen-Summaries und Tages-Summaries des Monats sammeln
        year, mon = month.split("-")
        summaries = []

        # Alle Tages-Summaries des Monats
        for day in range(1, 32):
            try:
                date = f"{year}-{mon}-{day:02d}"
                # Pruefen ob Datum gueltig
                datetime.strptime(date, "%Y-%m-%d")
                day_summary = await self._get_summary(date, DAILY)
                if day_summary:
                    summaries.append(f"[{date}]: {day_summary}")
            except ValueError:
                break  # Ungeltiges Datum (z.B. 31. Feb)

        if not summaries:
            logger.info("Keine Summaries fuer Monat %s", month)
            return None

        prompt = self._build_monthly_prompt(month, summaries)
        summary = await self._generate_summary(prompt, self.max_tokens_monthly)

        if summary:
            await self._store_summary(month, MONTHLY, summary)
            logger.info("Monats-Summary fuer %s erstellt", month)

        return summary

    # ----- Suche in Summaries -----

    async def search_summaries(self, query: str, limit: int = 5) -> list[dict]:
        """Sucht in allen Zusammenfassungen per Vektor-Suche."""
        if not self.chroma_collection:
            return []

        try:
            results = self.chroma_collection.query(
                query_texts=[query],
                n_results=limit,
                where={"type": {"$in": [DAILY, WEEKLY, MONTHLY]}},
            )

            summaries = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                    summaries.append({
                        "content": doc,
                        "date": meta.get("date", ""),
                        "summary_type": meta.get("type", ""),
                        "relevance": results["distances"][0][i]
                        if results.get("distances")
                        else 0,
                    })
            return summaries
        except Exception as e:
            logger.error("Fehler bei Summary-Suche: %s", e)
            return []

    async def get_recent_summaries(self, limit: int = 7) -> list[dict]:
        """Holt die neuesten Zusammenfassungen."""
        if not self.redis:
            return []

        try:
            keys = []
            cursor = 0
            while True:
                cursor, batch = await self.redis.scan(
                    cursor, match="mha:summary:daily:*", count=100
                )
                keys.extend(batch)
                if cursor == 0:
                    break

            # Nach Datum sortieren (neueste zuerst)
            keys.sort(reverse=True)
            keys = keys[:limit]

            summaries = []
            for key in keys:
                content = await self.redis.get(key)
                if content:
                    date = key.replace("mha:summary:daily:", "")
                    summaries.append({"date": date, "content": content})
            return summaries
        except Exception as e:
            logger.error("Fehler beim Laden der Summaries: %s", e)
            return []

    # ----- Private Hilfsmethoden -----

    async def _get_conversations_for_date(self, date: str) -> list[dict]:
        """Holt alle Konversationen eines bestimmten Tages."""
        # Primaer: MemoryManager Archiv (Phase 7)
        if self.memory:
            convs = await self.memory.get_conversations_for_date(date)
            if convs:
                return convs

        # Fallback: Working Memory durchsuchen
        if not self.redis:
            return []

        try:
            all_convs = await self.redis.lrange("mha:conversations", 0, -1)
            day_convs = []
            for entry in all_convs:
                conv = json.loads(entry)
                ts = conv.get("timestamp", "")
                if ts.startswith(date):
                    day_convs.append(conv)
            day_convs.sort(key=lambda x: x.get("timestamp", ""))
            return day_convs
        except Exception as e:
            logger.error("Fehler beim Laden der Konversationen fuer %s: %s", date, e)
            return []

    async def _generate_summary(self, prompt: str, max_tokens: int) -> Optional[str]:
        """Generiert eine Zusammenfassung via LLM."""
        try:
            response = await self.ollama.chat(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                max_tokens=max_tokens,
            )

            content = response.get("message", {}).get("content", "")
            if content:
                return content.strip()
            return None
        except Exception as e:
            logger.error("Fehler bei LLM-Zusammenfassung: %s", e)
            return None

    async def _store_summary(self, date: str, summary_type: str, content: str):
        """Speichert eine Zusammenfassung in Redis und ChromaDB."""
        # Redis (schneller Zugriff)
        if self.redis:
            key = f"mha:summary:{summary_type}:{date}"
            await self.redis.set(key, content)

        # ChromaDB (Vektor-Suche)
        if self.chroma_collection:
            try:
                doc_id = f"summary_{summary_type}_{date}"
                self.chroma_collection.upsert(
                    documents=[content],
                    metadatas=[{
                        "date": date,
                        "type": summary_type,
                        "created_at": datetime.now().isoformat(),
                    }],
                    ids=[doc_id],
                )
            except Exception as e:
                logger.error("Fehler beim Speichern in ChromaDB: %s", e)

    async def _get_summary(self, date: str, summary_type: str) -> Optional[str]:
        """Holt eine existierende Zusammenfassung."""
        if not self.redis:
            return None
        return await self.redis.get(f"mha:summary:{summary_type}:{date}")

    def _get_system_prompt(self) -> str:
        return """Du bist der MindHome Assistant Memory Processor.
Deine Aufgabe: Erstelle KURZE, praezise Zusammenfassungen von Gespraechen und Ereignissen.
Sprache: Deutsch.
Fokus auf: Wichtige Fakten, Stimmungen, Muster, Praeferenzen.
KEINE Floskeln. Nur Inhalt.
Format: Fliesstext, kurze Saetze."""

    def _build_daily_prompt(self, date: str, conversations: list[dict]) -> str:
        parts = [f"Erstelle eine Tages-Zusammenfassung fuer {date}.\n"]
        parts.append("Konversationen des Tages:\n")

        for conv in conversations:
            role = "User" if conv["role"] == "user" else "Assistant"
            time = conv.get("timestamp", "")[:16]  # YYYY-MM-DDTHH:MM
            parts.append(f"[{time}] {role}: {conv['content']}")

        parts.append("\nFasse zusammen: Was wurde besprochen? "
                     "Welche Aktionen? Stimmung? Besonderheiten?")
        parts.append("Maximal 200 Woerter.")

        return "\n".join(parts)

    def _build_weekly_prompt(self, week: str, daily_summaries: list[str]) -> str:
        parts = [f"Erstelle eine Wochen-Zusammenfassung fuer die Woche {week}.\n"]
        parts.append("Tages-Zusammenfassungen:\n")

        for summary in daily_summaries:
            parts.append(summary)

        parts.append("\nFasse die Woche zusammen: Muster, Trends, "
                     "wichtige Ereignisse, Stimmungsverlauf.")
        parts.append("Maximal 150 Woerter.")

        return "\n".join(parts)

    def _build_monthly_prompt(self, month: str, summaries: list[str]) -> str:
        parts = [f"Erstelle eine Monats-Zusammenfassung fuer {month}.\n"]
        parts.append("Zusammenfassungen des Monats:\n")

        for summary in summaries:
            parts.append(summary)

        parts.append("\nFasse den Monat zusammen: Uebergreifende Muster, "
                     "Veraenderungen, wichtige Meilensteine.")
        parts.append("Maximal 200 Woerter.")

        return "\n".join(parts)
