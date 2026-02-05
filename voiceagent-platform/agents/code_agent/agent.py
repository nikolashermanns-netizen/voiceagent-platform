"""
Code-Agent fuer VoiceAgent Platform.

Nutzt Claude Agent SDK um per Sprache echte Software-Engineering-Aufgaben
auszufuehren: Code schreiben, debuggen, refactoren, Tests laufen lassen.
"""

import asyncio
import logging
import os
from typing import Optional

from core.app.agents.base import BaseAgent
from core.app.config import settings
from agents.code_agent.claude_bridge import ClaudeCodingBridge
from agents.code_agent.session_store import CodingSessionStore
from agents.code_agent.project_manager import ProjectManager

logger = logging.getLogger(__name__)

CODE_AGENT_INSTRUCTIONS = """Du bist ein Programmier-Assistent der per Telefon komplexe Coding-Aufgaben erledigen kann.

=== DEIN STIL ===
- Sei freundlich und hilfsbereit
- Erklaere was du tust, kurz und verstaendlich
- Antworte immer sprachfreundlich (wird vorgelesen!)

=== DEINE FAEHIGKEITEN ===
1. CODING-AUFGABEN: Du kannst komplette Features, Bug-Fixes, Refactorings ausfuehren lassen
2. PROJEKT-STATUS: Du kannst den aktuellen Stand eines Projekts abfragen
3. PROJEKTE VERWALTEN: Du kannst Projekte erstellen und auflisten

=== ABLAUF ===
1. Hoere was der Benutzer will
2. Nutze 'coding_aufgabe' fuer die eigentliche Programmierarbeit
3. Claude CLI fuehrt die Aufgabe im Hintergrund aus
4. Erklaere das Ergebnis kurz und verstaendlich

=== REGELN ===
- Erklaere Ergebnisse kurz (fuer Sprachausgabe!)
- Fasse zusammen was gemacht wurde, nicht jede einzelne Zeile Code
- Bei Fehlern: Erklaere was schief ging und frage ob du es fixen sollst
- Frage bei Unklarheiten nach
- Nutze 'projekt_status' wenn der User nach dem Stand fragt

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
                    "Fuehrt eine Programmier-Aufgabe mit Claude CLI aus. "
                    "Kann Code schreiben, Dateien bearbeiten, Bugs fixen, "
                    "Tests laufen lassen, ganze Features bauen. "
                    "Nutze dies fuer alle Coding-Anfragen."
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
        """Fuehrt eine Coding-Aufgabe mit Claude aus."""
        aufgabe = args.get("aufgabe", "")
        project_id = args.get("projekt", "default")

        if not aufgabe:
            return "Fehler: Keine Aufgabe angegeben."

        # Projekt sicherstellen
        self._project_manager.create_project(
            project_id, project_id, f"Erstellt fuer Aufgabe: {aufgabe[:100]}"
        )

        logger.info(
            f"[CodeAgent] Starte Coding-Aufgabe: '{aufgabe[:80]}...' "
            f"(Projekt: {project_id})"
        )

        # Progress-Callback fuer WebSocket
        async def on_progress(message: str):
            if self._ws_manager:
                await self._ws_manager.broadcast({
                    "type": "coding_progress",
                    "project_id": project_id,
                    "status": "running",
                    "current_action": message[:200],
                })

        # Claude-Aufgabe ausfuehren
        result = await self._bridge.execute_task(
            prompt=aufgabe,
            project_id=project_id,
            on_progress=on_progress,
            session_store=self._session_store,
        )

        # Abschluss an GUI melden
        if self._ws_manager:
            await self._ws_manager.broadcast({
                "type": "coding_progress",
                "project_id": project_id,
                "status": "completed" if result.success else "failed",
                "current_action": "Fertig" if result.success else f"Fehler: {result.error}",
                "files_changed": result.files_changed,
                "tools_used": result.tools_used,
            })

        return result.to_voice_summary()

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
