"""
Projekt-Planer fuer Ideas-Agent.

Erstellt Projekte aus Ideen und plant deren Umsetzung.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from core.app.db.database import Database

logger = logging.getLogger(__name__)


class Project:
    """Ein Projekt."""

    def __init__(self, id: str = None, title: str = "",
                 description: str = "", status: str = "planning",
                 ideas: list = None, tasks: list = None,
                 plan: str = "", milestones: list = None,
                 created_at: str = None, updated_at: str = None):
        self.id = id or str(uuid.uuid4())[:8]
        self.title = title
        self.description = description
        self.status = status
        self.ideas = ideas or []
        self.tasks = tasks or []
        self.plan = plan
        self.milestones = milestones or []
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "ideas": self.ideas,
            "tasks": self.tasks,
            "plan": self.plan,
            "milestones": self.milestones,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_speech(self) -> str:
        """Fuer Sprachausgabe."""
        parts = [f"Projekt: {self.title}"]
        if self.description:
            parts.append(self.description)
        parts.append(f"Status: {self.status}")
        if self.milestones:
            parts.append(f"{len(self.milestones)} Meilensteine definiert")
        return ". ".join(parts)


class ProjectPlanner:
    """Verwaltet Projekte in SQLite."""

    def __init__(self, db: Database):
        self.db = db

    async def create(self, project: Project) -> Project:
        """Erstellt ein neues Projekt."""
        await self.db.execute(
            """INSERT INTO projects (id, title, description, status, ideas, tasks, plan, milestones)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (project.id, project.title, project.description, project.status,
             json.dumps(project.ideas), json.dumps(project.tasks),
             project.plan, json.dumps(project.milestones))
        )
        logger.info(f"Projekt erstellt: {project.id} ({project.title})")
        return project

    async def get(self, project_id: str) -> Optional[Project]:
        """Gibt ein Projekt zurueck."""
        row = await self.db.fetchone(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        if row:
            return self._row_to_project(row)
        return None

    async def get_all(self, status: str = None) -> list[Project]:
        """Gibt alle Projekte zurueck."""
        query = "SELECT * FROM projects"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"
        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_project(row) for row in rows]

    async def update(self, project: Project) -> Project:
        """Aktualisiert ein Projekt."""
        project.updated_at = datetime.now().isoformat()
        await self.db.execute(
            """UPDATE projects SET title=?, description=?, status=?,
               ideas=?, tasks=?, plan=?, milestones=?, updated_at=? WHERE id=?""",
            (project.title, project.description, project.status,
             json.dumps(project.ideas), json.dumps(project.tasks),
             project.plan, json.dumps(project.milestones),
             project.updated_at, project.id)
        )
        return project

    async def add_idea_to_project(self, project_id: str, idea_id: str) -> Optional[Project]:
        """Verknuepft eine Idee mit einem Projekt."""
        project = await self.get(project_id)
        if not project:
            return None

        if idea_id not in project.ideas:
            project.ideas.append(idea_id)
            return await self.update(project)
        return project

    def _row_to_project(self, row: dict) -> Project:
        """Konvertiert DB-Row zu Project."""
        return Project(
            id=row["id"],
            title=row["title"],
            description=row.get("description", ""),
            status=row.get("status", "planning"),
            ideas=json.loads(row.get("ideas", "[]")) if isinstance(row.get("ideas"), str) else [],
            tasks=json.loads(row.get("tasks", "[]")) if isinstance(row.get("tasks"), str) else [],
            plan=row.get("plan", ""),
            milestones=json.loads(row.get("milestones", "[]")) if isinstance(row.get("milestones"), str) else [],
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )
