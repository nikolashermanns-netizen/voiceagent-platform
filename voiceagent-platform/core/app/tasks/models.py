"""
Task-Datenmodell fuer asynchrone Aufgaben.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    """Eine asynchrone Aufgabe die von einem Agenten bearbeitet wird."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    progress: float = 0.0
    caller_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def to_speech(self) -> str:
        """Gibt eine sprachfreundliche Zusammenfassung zurueck."""
        status_text = {
            TaskStatus.PENDING: "wartet noch",
            TaskStatus.RUNNING: f"in Bearbeitung, {int(self.progress * 100)} Prozent",
            TaskStatus.COMPLETED: "fertig",
            TaskStatus.FAILED: "fehlgeschlagen",
            TaskStatus.CANCELLED: "abgebrochen",
        }
        text = f"{self.description} - {status_text.get(self.status, self.status)}"
        if self.status == TaskStatus.COMPLETED and self.result:
            # Ergebnis auf max 200 Zeichen kuerzen
            short_result = self.result[:200]
            text += f". Ergebnis: {short_result}"
        elif self.status == TaskStatus.FAILED and self.error:
            text += f". Fehler: {self.error[:100]}"
        return text
