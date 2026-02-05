"""
Ideen-Store fuer Ideas-Agent.

CRUD-Operationen fuer Ideen in SQLite.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from core.app.db.database import Database

logger = logging.getLogger(__name__)


class Idea:
    """Eine Idee."""

    def __init__(self, id: str = None, title: str = "",
                 description: str = "", category: str = "",
                 priority: int = 0, status: str = "new",
                 tags: list = None, notes: list = None,
                 created_at: str = None, updated_at: str = None):
        self.id = id or str(uuid.uuid4())[:8]
        self.title = title
        self.description = description
        self.category = category
        self.priority = priority
        self.status = status
        self.tags = tags or []
        self.notes = notes or []
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "tags": self.tags,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_speech(self) -> str:
        """Fuer Sprachausgabe."""
        parts = [f"Idee: {self.title}"]
        if self.description:
            parts.append(f"Beschreibung: {self.description}")
        if self.category:
            parts.append(f"Kategorie: {self.category}")
        parts.append(f"Status: {self.status}")
        return ". ".join(parts)


class IdeaStore:
    """CRUD fuer Ideen in SQLite."""

    def __init__(self, db: Database):
        self.db = db

    async def create(self, idea: Idea) -> Idea:
        """Erstellt eine neue Idee."""
        await self.db.execute(
            """INSERT INTO ideas (id, title, description, category, priority, status, tags, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (idea.id, idea.title, idea.description, idea.category,
             idea.priority, idea.status,
             json.dumps(idea.tags), json.dumps(idea.notes))
        )
        logger.info(f"Idee erstellt: {idea.id} ({idea.title})")
        return idea

    async def get(self, idea_id: str) -> Optional[Idea]:
        """Gibt eine Idee zurueck."""
        row = await self.db.fetch_one(
            "SELECT * FROM ideas WHERE id = ?", (idea_id,)
        )
        if row:
            return self._row_to_idea(row)
        return None

    async def get_all(self, status: str = None, category: str = None) -> list[Idea]:
        """Gibt alle Ideen zurueck, optional gefiltert."""
        query = "SELECT * FROM ideas"
        params = []
        conditions = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._row_to_idea(row) for row in rows]

    async def update(self, idea: Idea) -> Idea:
        """Aktualisiert eine Idee."""
        idea.updated_at = datetime.now().isoformat()
        await self.db.execute(
            """UPDATE ideas SET title=?, description=?, category=?, priority=?,
               status=?, tags=?, notes=?, updated_at=? WHERE id=?""",
            (idea.title, idea.description, idea.category, idea.priority,
             idea.status, json.dumps(idea.tags), json.dumps(idea.notes),
             idea.updated_at, idea.id)
        )
        return idea

    async def archive(self, idea_id: str) -> Optional[Idea]:
        """Archiviert eine Idee (Status auf 'archived' setzen, niemals loeschen)."""
        idea = await self.get(idea_id)
        if not idea:
            return None
        idea.status = "archived"
        await self.update(idea)
        logger.info(f"Idee archiviert: {idea_id} ({idea.title})")
        return idea

    async def add_note(self, idea_id: str, note: str) -> Optional[Idea]:
        """Fuegt eine Notiz zu einer Idee hinzu."""
        idea = await self.get(idea_id)
        if not idea:
            return None

        idea.notes.append({
            "text": note,
            "timestamp": datetime.now().isoformat()
        })
        return await self.update(idea)

    def _row_to_idea(self, row: dict) -> Idea:
        """Konvertiert DB-Row zu Idea."""
        tags = json.loads(row.get("tags", "[]")) if isinstance(row.get("tags"), str) else []
        notes = json.loads(row.get("notes", "[]")) if isinstance(row.get("notes"), str) else []

        return Idea(
            id=row["id"],
            title=row["title"],
            description=row.get("description", ""),
            category=row.get("category", ""),
            priority=row.get("priority", 0),
            status=row.get("status", "new"),
            tags=tags,
            notes=notes,
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )
