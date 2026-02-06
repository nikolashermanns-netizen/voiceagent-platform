"""
Code-Agent fuer VoiceAgent Platform.

Nutzt Claude Agent SDK um per Sprache echte Software-Engineering-Aufgaben
auszufuehren: Code schreiben, debuggen, refactoren, Tests laufen lassen.

Coding-Aufgaben laufen im Hintergrund als asyncio.Task, damit der
Voice-Agent waehrend der Ausfuehrung weiter ansprechbar bleibt.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.app.agents.base import BaseAgent
from core.app.config import settings
from agents.code_agent.claude_bridge import ClaudeCodingBridge, CodingResult
from agents.code_agent.session_store import CodingSessionStore
from agents.code_agent.project_manager import ProjectManager

logger = logging.getLogger(__name__)


@dataclass
class BackgroundTask:
    """Zustand einer Hintergrund-Coding-Aufgabe."""
    task_id: str
    aufgabe: str
    projekt: str
    status: str  # "running" | "completed" | "failed"
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    result: Optional[CodingResult] = None
    progress_messages: list[str] = field(default_factory=list)


CODE_AGENT_INSTRUCTIONS = """Du bist ein Programmier-Assistent der per Telefon komplexe Coding-Aufgaben erledigen kann.

=== DEIN STIL ===
- Sei freundlich und hilfsbereit
- Erklaere was du tust, kurz und verstaendlich
- Antworte immer sprachfreundlich (wird vorgelesen!)

=== DEINE FAEHIGKEITEN ===
1. CODING-AUFGABEN: Du kannst komplette Features, Bug-Fixes, Refactorings ausfuehren lassen
2. AUFGABE-STATUS: Du kannst pruefen ob eine Aufgabe noch laeuft oder fertig ist
3. PROJEKT-STATUS: Du kannst den aktuellen Stand eines Projekts abfragen
4. PROJEKTE VERWALTEN: Du kannst Projekte erstellen und auflisten

=== ABLAUF ===
1. Hoere was der Benutzer will
2. Nutze 'coding_aufgabe' - die Aufgabe startet im Hintergrund
3. Sage dem Benutzer dass die Aufgabe gestartet wurde
4. Wenn der Benutzer nach dem Status fragt, nutze 'aufgabe_status'
5. Wenn 'aufgabe_status' meldet dass die Aufgabe fertig ist, erklaere das Ergebnis

=== WICHTIG: HINTERGRUND-AUFGABEN ===
- 'coding_aufgabe' startet die Arbeit im Hintergrund und kehrt sofort zurueck
- Die eigentliche Ausfuehrung dauert typischerweise 30 Sekunden bis mehrere Minuten
- Nutze 'aufgabe_status' um den Fortschritt zu pruefen
- Du kannst waehrend der Ausfuehrung normal mit dem Benutzer sprechen
- Wenn der Benutzer fragt "ist es fertig?", "wie weit bist du?" oder "was macht Claude?", nutze 'aufgabe_status'

=== REGELN ===
- Erklaere Ergebnisse kurz (fuer Sprachausgabe!)
- Fasse zusammen was gemacht wurde, nicht jede einzelne Zeile Code
- Bei Fehlern: Erklaere was schief ging und frage ob du es fixen sollst
- Frage bei Unklarheiten nach
- Nutze 'projekt_status' wenn der User nach dem Stand eines Projekts fragt

=== ZURUECK ZUR ZENTRALE ===
Wenn der Anrufer "exit", "zurueck", "menue" oder "hauptmenue" sagt:
- Sage kurz: "Alles klar, ich bringe dich zurueck zur Zentrale."
- Nutze dann SOFORT das Tool 'zurueck_zur_zentrale'"""


class CodeAgent(BaseAgent):
    """Agent fuer Code-Erstellung mit Claude Agent SDK."""

    def __init__(self):
        self._bridge = ClaudeCodingBridge(settings.WORKSPACE_DIR)
        self._session_store = CodingSessionStore(
            os.path.join(os.path.dirname(settings.DATABASE_PATH), "coding_sessions.db")
        )
        self._project_manager = ProjectManager()
        self._current_project = "default"
        self._ws_manager = None  # Wird via set_ws_manager gesetzt
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._current_task: Optional[BackgroundTask] = None
        self._last_completed_task: Optional[BackgroundTask] = None
        self._task_counter: int = 0

    def set_ws_manager(self, ws_manager):
        """Setzt den WebSocket-Manager fuer Progress-Updates."""
        self._ws_manager = ws_manager

    @property
    def name(self) -> str:
        return "code_agent"

    @property
    def display_name(self) -> str:
        return "Programmier-Assistent"

    @property
    def description(self) -> str:
        return (
            "Programmier-Assistent mit Claude CLI. Kann komplette Features bauen, "
            "Bugs fixen, Code refactoren und Tests laufen lassen."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "programmieren", "code", "script", "automatisierung",
            "berechnung", "debugging", "refactoring", "testing",
        ]

    @property
    def keywords(self) -> list[str]:
        return [
            "programmieren", "code", "python", "javascript", "typescript",
            "script", "berechne", "rechne", "programm", "funktion",
            "algorithmus", "automatisiere", "skript", "bash", "api",
            "feature", "bug", "fix", "refactor", "test", "deploy",
            "erstelle", "baue", "implementiere", "entwickle",
        ]

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "coding_aufgabe",
                "description": (
                    "Startet eine Programmier-Aufgabe mit Claude CLI im Hintergrund. "
                    "Kann Code schreiben, Dateien bearbeiten, Bugs fixen, "
                    "Tests laufen lassen, ganze Features bauen. "
                    "Kehrt sofort zurueck - die Aufgabe laeuft im Hintergrund. "
                    "Nutze 'aufgabe_status' um den Fortschritt zu pruefen."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "aufgabe": {
                            "type": "string",
                            "description": (
                                "Detaillierte Beschreibung der Aufgabe. "
                                "Z.B. 'Erstelle eine FastAPI Route fuer User-Registration "
                                "mit Endpoints POST /register, POST /login und GET /me. "
                                "Nutze SQLite und Pydantic.'"
                            ),
                        },
                        "projekt": {
                            "type": "string",
                            "description": (
                                "Projekt-Name. Wird als Ordnername verwendet. "
                                "Z.B. 'user-api', 'web-scraper', 'daten-analyse'. "
                                "Falls nicht angegeben wird 'default' verwendet."
                            ),
                        },
                    },
                    "required": ["aufgabe"],
                },
            },
            {
                "type": "function",
                "name": "aufgabe_status",
                "description": (
                    "Prueft den Status der aktuellen oder letzten Coding-Aufgabe. "
                    "Nutze dies wenn der Benutzer fragt ob die Aufgabe fertig ist, "
                    "was Claude gerade macht, oder nach dem Ergebnis fragt."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "type": "function",
                "name": "projekt_status",
                "description": (
                    "Zeigt den aktuellen Stand eines Projekts. "
                    "Welche Dateien gibt es, was wurde bisher gemacht."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "projekt": {
                            "type": "string",
                            "description": "Projekt-Name. Falls nicht angegeben wird 'default' verwendet.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "type": "function",
                "name": "projekte_auflisten",
                "description": "Listet alle vorhandenen Projekte auf.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "type": "function",
                "name": "session_zuruecksetzen",
                "description": (
                    "Setzt die Coding-Session eines Projekts zurueck. "
                    "Claude vergisst dann den bisherigen Kontext fuer dieses Projekt."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "projekt": {
                            "type": "string",
                            "description": "Projekt-Name dessen Session zurueckgesetzt werden soll.",
                        },
                    },
                    "required": ["projekt"],
                },
            },
            {
                "type": "function",
                "name": "zurueck_zur_zentrale",
                "description": (
                    "Kehrt zurueck zur Zentrale. Nutze dies wenn der Anrufer "
                    "'exit', 'zurueck', 'menue' oder 'hauptmenue' sagt."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    def get_instructions(self) -> str:
        return CODE_AGENT_INSTRUCTIONS

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        logger.info(f"[CodeAgent] Tool: {tool_name}, Args: {arguments}")

        if tool_name == "coding_aufgabe":
            return await self._coding_aufgabe(arguments)
        elif tool_name == "aufgabe_status":
            return await self._aufgabe_status()
        elif tool_name == "projekt_status":
            return await self._projekt_status(arguments)
        elif tool_name == "projekte_auflisten":
            return await self._projekte_auflisten()
        elif tool_name == "session_zuruecksetzen":
            return await self._session_zuruecksetzen(arguments)
        elif tool_name == "zurueck_zur_zentrale":
            return "__SWITCH__:main_agent"
        else:
            return f"Unbekannte Funktion: {tool_name}"

    async def _coding_aufgabe(self, args: dict) -> str:
        """Startet eine Coding-Aufgabe im Hintergrund."""
        aufgabe = args.get("aufgabe", "")
        project_id = args.get("projekt", "default")

        if not aufgabe:
            return "Fehler: Keine Aufgabe angegeben."

        # Pruefen ob bereits eine Aufgabe laeuft
        if self._current_task and self._current_task.status == "running":
            return (
                f"Es laeuft bereits eine Aufgabe: '{self._current_task.aufgabe[:80]}'. "
                "Bitte warte bis sie fertig ist. Frage nach dem Status mit aufgabe_status."
            )

        # Projekt sicherstellen
        self._project_manager.create_project(
            project_id, project_id, f"Erstellt fuer Aufgabe: {aufgabe[:100]}"
        )

        # BackgroundTask erstellen
        self._task_counter += 1
        task = BackgroundTask(
            task_id=f"task-{self._task_counter}",
            aufgabe=aufgabe,
            projekt=project_id,
            status="running",
        )
        self._current_task = task

        logger.info(
            f"[CodeAgent] Starte Background-Task: '{aufgabe[:80]}...' "
            f"(Projekt: {project_id})"
        )

        # Im Hintergrund starten
        asyncio_task = asyncio.create_task(self._run_coding_background(task))
        self._running_tasks[task.task_id] = asyncio_task

        return (
            f"Ich habe die Aufgabe gestartet: '{aufgabe[:100]}'. "
            "Das dauert einen Moment. Du kannst mich jederzeit nach dem Status fragen."
        )

    async def _run_coding_background(self, task: BackgroundTask):
        """Fuehrt die Coding-Aufgabe im Hintergrund aus."""
        try:
            async def on_progress(message: str):
                task.progress_messages.append(message[:200])
                # Nur die letzten 20 Messages behalten
                if len(task.progress_messages) > 20:
                    task.progress_messages = task.progress_messages[-20:]
                if self._ws_manager:
                    await self._ws_manager.broadcast({
                        "type": "coding_progress",
                        "project_id": task.projekt,
                        "status": "running",
                        "current_action": message[:200],
                    })

            result = await self._bridge.execute_task(
                prompt=task.aufgabe,
                project_id=task.projekt,
                on_progress=on_progress,
                session_store=self._session_store,
            )

            task.result = result
            task.status = "completed" if result.success else "failed"
            task.finished_at = datetime.now()

            # GUI informieren
            if self._ws_manager:
                await self._ws_manager.broadcast({
                    "type": "coding_progress",
                    "project_id": task.projekt,
                    "status": task.status,
                    "current_action": "Fertig" if result.success else f"Fehler: {result.error}",
                    "files_changed": result.files_changed,
                    "tools_used": result.tools_used,
                })

            logger.info(f"[CodeAgent] Background-Task {task.task_id} abgeschlossen: {task.status}")

        except asyncio.CancelledError:
            task.status = "failed"
            task.result = CodingResult(success=False, error="Aufgabe abgebrochen")
            task.finished_at = datetime.now()
            logger.info(f"[CodeAgent] Background-Task {task.task_id} abgebrochen")

        except Exception as e:
            task.status = "failed"
            task.result = CodingResult(success=False, error=str(e))
            task.finished_at = datetime.now()
            logger.error(f"[CodeAgent] Background-Task Fehler: {e}", exc_info=True)

        finally:
            self._last_completed_task = task
            self._running_tasks.pop(task.task_id, None)

    async def _aufgabe_status(self) -> str:
        """Gibt den Status der aktuellen/letzten Aufgabe zurueck."""
        task = self._current_task
        if task is None:
            task = self._last_completed_task
        if task is None:
            return "Es wurde noch keine Aufgabe gestartet."

        if task.status == "running":
            elapsed = (datetime.now() - task.started_at).seconds
            status = f"Aufgabe laeuft seit {elapsed} Sekunden: '{task.aufgabe[:80]}'"
            if task.progress_messages:
                last_msg = task.progress_messages[-1]
                status += f"\nLetzter Schritt: {last_msg[:150]}"
            return status

        elif task.status == "completed" and task.result:
            return f"Aufgabe abgeschlossen! {task.result.to_voice_summary()}"

        elif task.status == "failed":
            error = task.result.error if task.result else "Unbekannter Fehler"
            return f"Aufgabe fehlgeschlagen: {error}"

        return "Status unbekannt."

    async def _projekt_status(self, args: dict) -> str:
        """Fragt den Projekt-Status ab."""
        project_id = args.get("projekt", "default")

        # Schnelle Dateiliste
        files = self._project_manager.list_files(project_id)
        if not files:
            return f"Projekt '{project_id}' ist leer. Noch keine Dateien vorhanden."

        # Claude fuer detaillierten Status nutzen
        status = await self._bridge.get_project_status(project_id)
        return status

    async def _projekte_auflisten(self) -> str:
        """Listet alle Projekte auf."""
        projects = self._project_manager.list_projects()
        if not projects:
            return "Noch keine Projekte vorhanden."

        lines = ["Vorhandene Projekte:"]
        for p in projects:
            name = p.get("name", p.get("id", "?"))
            file_count = len(self._project_manager.list_files(p["id"]))
            lines.append(f"- {name}: {file_count} Dateien")

        return "\n".join(lines)

    async def _session_zuruecksetzen(self, args: dict) -> str:
        """Setzt die Claude-Session eines Projekts zurueck."""
        project_id = args.get("projekt", "default")

        self._bridge.clear_session(project_id)
        await self._session_store.clear_session(project_id)

        return f"Session fuer Projekt '{project_id}' wurde zurueckgesetzt. Claude startet beim naechsten Auftrag ohne Kontext."

    async def on_call_start(self, caller_id: str):
        """Setup bei Anrufbeginn."""
        logger.info(f"[CodeAgent] Call gestartet: {caller_id}")

    async def on_call_end(self, caller_id: str):
        """Cleanup bei Anrufende."""
        logger.info(f"[CodeAgent] Call beendet: {caller_id}")
        # Laufende Tasks nicht abbrechen - die laufen im Hintergrund weiter


def create_agent() -> BaseAgent:
    """Factory-Funktion fuer Agent-Discovery."""
    return CodeAgent()
