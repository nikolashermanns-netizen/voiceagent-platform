"""
CodingSessionStore - Persistiert Claude-Sessions pro Projekt.

Speichert Session-IDs in SQLite, damit Folge-Auftraege
den Kontext der vorherigen Session behalten.
"""

import logging
from datetime import datetime
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


class SessionInfo:
    """Metadaten einer gespeicherten Session."""

    def __init__(self, project_id: str, session_id: str,
                 summary: str, created_at: str):
        self.project_id = project_id
        self.session_id = session_id
        self.summary = summary
        self.created_at = created_at


class CodingSessionStore:
    """
    Persistiert Claude-Sessions pro Projekt in SQLite.

    Schema:
        coding_sessions(project_id, session_id, summary, created_at, updated_at)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialized = False

    async def _ensure_table(self):
        """Erstellt die Tabelle falls sie nicht existiert."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS coding_sessions (
                    project_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    summary TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.commit()

        self._initialized = True

    async def save_session(self, project_id: str, session_id: str,
                           summary: str = ""):
        """Speichert oder aktualisiert eine Session."""
        await self._ensure_table()
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO coding_sessions (project_id, session_id, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
            """, (project_id, session_id, summary, now, now))
            await db.commit()

        logger.info(f"[SessionStore] Session gespeichert: {project_id} -> {session_id[:12]}...")

    async def get_session(self, project_id: str) -> Optional[str]:
        """Gibt die Session-ID fuer ein Projekt zurueck."""
        await self._ensure_table()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT session_id FROM coding_sessions WHERE project_id = ?",
                (project_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def list_sessions(self) -> list[SessionInfo]:
        """Listet alle gespeicherten Sessions auf."""
        await self._ensure_table()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT project_id, session_id, summary, created_at "
                "FROM coding_sessions ORDER BY updated_at DESC"
            )
            rows = await cursor.fetchall()
            return [
                SessionInfo(
                    project_id=row[0],
                    session_id=row[1],
                    summary=row[2],
                    created_at=row[3],
                )
                for row in rows
            ]

    async def clear_session(self, project_id: str):
        """Loescht die Session fuer ein Projekt."""
        await self._ensure_table()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM coding_sessions WHERE project_id = ?",
                (project_id,)
            )
            await db.commit()

        logger.info(f"[SessionStore] Session geloescht: {project_id}")

    async def clear_all(self):
        """Loescht alle Sessions."""
        await self._ensure_table()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM coding_sessions")
            await db.commit()

        logger.info("[SessionStore] Alle Sessions geloescht")
