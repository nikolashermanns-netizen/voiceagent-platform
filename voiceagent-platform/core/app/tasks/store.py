"""
Task-Persistierung mit SQLite.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from core.app.tasks.models import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskStore:
    """CRUD-Operationen fuer Tasks."""

    def __init__(self, db):
        self.db = db

    async def create(self, task: Task) -> Task:
        """Task in DB speichern."""
        await self.db.execute(
            """INSERT INTO tasks (id, agent_name, description, status, result, error,
               progress, caller_id, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.agent_name, task.description, task.status.value,
             task.result, task.error, task.progress, task.caller_id,
             json.dumps(task.metadata), task.created_at.isoformat(),
             task.updated_at.isoformat())
        )
        logger.info(f"Task erstellt: {task.id} ({task.description[:50]})")
        return task

    async def get(self, task_id: str) -> Optional[Task]:
        """Task aus DB laden."""
        row = await self.db.fetch_one(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        if row:
            return self._row_to_task(row)
        return None

    async def update(self, task: Task) -> Task:
        """Task aktualisieren."""
        task.updated_at = datetime.now()
        await self.db.execute(
            """UPDATE tasks SET status=?, result=?, error=?, progress=?,
               metadata=?, updated_at=? WHERE id=?""",
            (task.status.value, task.result, task.error, task.progress,
             json.dumps(task.metadata), task.updated_at.isoformat(), task.id)
        )
        return task

    async def get_by_caller(self, caller_id: str, limit: int = 20) -> list[Task]:
        """Tasks eines Anrufers laden."""
        rows = await self.db.fetch_all(
            "SELECT * FROM tasks WHERE caller_id = ? ORDER BY created_at DESC LIMIT ?",
            (caller_id, limit)
        )
        return [self._row_to_task(row) for row in rows]

    async def get_by_status(self, status: TaskStatus, limit: int = 50) -> list[Task]:
        """Tasks nach Status laden."""
        rows = await self.db.fetch_all(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status.value, limit)
        )
        return [self._row_to_task(row) for row in rows]

    async def get_all(self, limit: int = 100) -> list[Task]:
        """Alle Tasks laden."""
        rows = await self.db.fetch_all(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [self._row_to_task(row) for row in rows]

    async def cancel(self, task_id: str) -> Optional[Task]:
        """Task abbrechen."""
        task = await self.get(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now()
            await self.update(task)
            logger.info(f"Task abgebrochen: {task_id}")
            return task
        return None

    def _row_to_task(self, row: dict) -> Task:
        """DB-Zeile zu Task konvertieren."""
        metadata = row.get("metadata", "{}")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Task(
            id=row["id"],
            agent_name=row["agent_name"],
            description=row.get("description", ""),
            status=TaskStatus(row.get("status", "pending")),
            result=row.get("result"),
            error=row.get("error"),
            progress=row.get("progress", 0.0),
            caller_id=row.get("caller_id"),
            metadata=metadata,
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else datetime.now(),
        )
