"""
Async Task-Executor fuer Hintergrund-Aufgaben.
"""

import asyncio
import logging
import traceback
from typing import Callable, Optional

from core.app.tasks.models import Task, TaskStatus
from core.app.tasks.store import TaskStore

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Fuehrt Tasks asynchron im Hintergrund aus."""

    def __init__(self, store: TaskStore):
        self.store = store
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._task_handlers: dict[str, Callable] = {}

    def register_handler(self, agent_name: str, handler: Callable):
        """Registriert einen Handler fuer einen Agent-Typ."""
        self._task_handlers[agent_name] = handler
        logger.info(f"Task-Handler registriert: {agent_name}")

    async def submit(self, task: Task) -> Task:
        """Task zur Ausfuehrung einreichen."""
        # In DB speichern
        task = await self.store.create(task)

        # Handler finden
        handler = self._task_handlers.get(task.agent_name)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error = f"Kein Handler fuer Agent '{task.agent_name}'"
            await self.store.update(task)
            return task

        # Async ausfuehren
        async_task = asyncio.create_task(self._run_task(task, handler))
        self._running_tasks[task.id] = async_task
        return task

    async def _run_task(self, task: Task, handler: Callable):
        """Fuehrt einen Task aus."""
        try:
            # Status auf Running setzen
            task.status = TaskStatus.RUNNING
            await self.store.update(task)

            # Handler ausfuehren
            result = await handler(task)

            # Ergebnis speichern
            task.status = TaskStatus.COMPLETED
            task.result = str(result) if result else "Erfolgreich abgeschlossen"
            task.progress = 1.0
            await self.store.update(task)

            logger.info(f"Task abgeschlossen: {task.id} ({task.description[:50]})")

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            await self.store.update(task)
            logger.info(f"Task abgebrochen: {task.id}")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = f"{type(e).__name__}: {str(e)}"
            await self.store.update(task)
            logger.error(f"Task fehlgeschlagen: {task.id} - {e}")

        finally:
            self._running_tasks.pop(task.id, None)

    async def cancel(self, task_id: str) -> Optional[Task]:
        """Laufenden Task abbrechen."""
        # Asyncio Task canceln
        async_task = self._running_tasks.get(task_id)
        if async_task:
            async_task.cancel()

        # In DB als cancelled markieren
        return await self.store.cancel(task_id)

    async def recover_pending(self):
        """Stellt pending/running Tasks nach Restart wieder her."""
        pending = await self.store.get_by_status(TaskStatus.PENDING)
        running = await self.store.get_by_status(TaskStatus.RUNNING)

        for task in running:
            # Running Tasks auf Failed setzen (waren beim Crash aktiv)
            task.status = TaskStatus.FAILED
            task.error = "Server-Neustart waehrend Ausfuehrung"
            await self.store.update(task)
            logger.info(f"Task nach Restart als failed markiert: {task.id}")

        for task in pending:
            # Pending Tasks neu einreichen
            handler = self._task_handlers.get(task.agent_name)
            if handler:
                async_task = asyncio.create_task(self._run_task(task, handler))
                self._running_tasks[task.id] = async_task
                logger.info(f"Pending Task wiederhergestellt: {task.id}")

    @property
    def active_count(self) -> int:
        """Anzahl aktiver Tasks."""
        return len(self._running_tasks)
