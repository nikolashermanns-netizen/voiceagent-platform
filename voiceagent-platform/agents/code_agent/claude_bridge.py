"""
ClaudeCodingBridge - Wrapper um claude-agent-sdk fuer den CodeAgent.

Fuehrt Coding-Aufgaben mit Claude CLI aus:
- Code schreiben, lesen, editieren
- Bash-Befehle ausfuehren (Tests, Build, Git)
- Codebase navigieren und verstehen
- Sessions pro Projekt persistieren
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from claude_agent_sdk import (
    ClaudeAgentOptions,
    query,
)

from core.app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CodingResult:
    """Ergebnis einer Claude Coding-Aufgabe."""
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None

    def to_voice_summary(self) -> str:
        """Sprachfreundliche Zusammenfassung."""
        if not self.success:
            return f"Die Aufgabe ist fehlgeschlagen: {self.error or 'Unbekannter Fehler'}"

        parts = []
        if self.summary:
            # Zusammenfassung auf ~500 Zeichen kuerzen fuer Sprachausgabe
            summary = self.summary
            if len(summary) > 500:
                summary = summary[:497] + "..."
            parts.append(summary)

        if self.files_changed:
            count = len(self.files_changed)
            if count == 1:
                parts.append(f"Eine Datei wurde geaendert: {self.files_changed[0]}")
            else:
                parts.append(f"{count} Dateien wurden geaendert.")

        return " ".join(parts) if parts else "Aufgabe abgeschlossen."


class ClaudeCodingBridge:
    """
    Bridge zwischen VoiceAgent CodeAgent und Claude Agent SDK.

    Fuehrt Coding-Aufgaben aus, trackt Sessions und streamt Progress.
    """

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self._sessions: dict[str, str] = {}  # project_id -> session_id

    def _get_project_dir(self, project_id: str) -> str:
        """Gibt das Arbeitsverzeichnis fuer ein Projekt zurueck."""
        project_dir = os.path.join(self.workspace_dir, project_id)
        os.makedirs(project_dir, exist_ok=True)
        return project_dir

    def _build_system_prompt(self, project_id: str) -> str:
        """Baut den System-Prompt fuer Claude."""
        return (
            f"Du arbeitest am Projekt '{project_id}' im Verzeichnis "
            f"{self._get_project_dir(project_id)}.\n\n"
            "Regeln:\n"
            "- Schreibe sauberen, gut strukturierten Code\n"
            "- Erstelle sinnvolle Verzeichnisstrukturen\n"
            "- Fuege Fehlerbehandlung hinzu wo noetig\n"
            "- Wenn Tests sinnvoll sind, erstelle sie\n"
            "- Halte dich an die Aufgabenbeschreibung\n"
            "- Antworte auf Deutsch\n"
            "- Fasse am Ende zusammen was du getan hast"
        )

    async def execute_task(
        self,
        prompt: str,
        project_id: str,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        session_store=None,
    ) -> CodingResult:
        """
        Fuehrt eine Coding-Aufgabe mit Claude aus.

        Args:
            prompt: Aufgabenbeschreibung
            project_id: Projekt-ID fuer Workspace und Session
            on_progress: Callback fuer Fortschritts-Updates
            session_store: Optional CodingSessionStore fuer Session-Persistierung

        Returns:
            CodingResult mit Zusammenfassung und geaenderten Dateien
        """
        project_dir = self._get_project_dir(project_id)

        # Session laden wenn vorhanden
        resume_session = self._sessions.get(project_id)
        if not resume_session and session_store:
            resume_session = await session_store.get_session(project_id)

        options = ClaudeAgentOptions(
            allowed_tools=settings.CLAUDE_ALLOWED_TOOLS,
            permission_mode="acceptEdits",
            cwd=project_dir,
            max_turns=settings.CLAUDE_MAX_TURNS,
            system_prompt=self._build_system_prompt(project_id),
        )

        if settings.CLAUDE_MAX_BUDGET > 0:
            options.max_budget_usd = settings.CLAUDE_MAX_BUDGET

        if settings.CLAUDE_MODEL:
            options.model = settings.CLAUDE_MODEL

        if resume_session:
            options.resume = resume_session

        result = CodingResult()
        result_parts = []

        try:
            async for message in query(prompt=prompt, options=options):
                msg_type = getattr(message, "type", None)

                if msg_type == "assistant":
                    content = getattr(message, "content", None)
                    if not content:
                        content = getattr(
                            getattr(message, "message", None), "content", []
                        )
                    for block in (content or []):
                        # Text-Block
                        if hasattr(block, "text") and block.text:
                            result_parts.append(block.text)
                            if on_progress:
                                # Nur erste 200 Zeichen pro Block senden
                                await on_progress(block.text[:200])

                        # Tool-Use-Block
                        if hasattr(block, "name") and block.name:
                            tool_name = block.name
                            result.tools_used.append(tool_name)
                            if on_progress:
                                await on_progress(f"[Tool: {tool_name}]")

                            # Datei-Aenderungen tracken
                            tool_input = getattr(block, "input", {}) or {}
                            if tool_name in ("Edit", "Write") and "file_path" in tool_input:
                                fpath = tool_input["file_path"]
                                if fpath not in result.files_changed:
                                    result.files_changed.append(fpath)

                elif msg_type == "result":
                    result_text = getattr(message, "result", "")
                    if result_text:
                        result_parts.append(result_text)

                    # Session-ID speichern
                    sid = getattr(message, "session_id", None)
                    if sid:
                        self._sessions[project_id] = sid
                        result.session_id = sid
                        if session_store:
                            summary = result_text[:200] if result_text else prompt[:200]
                            await session_store.save_session(project_id, sid, summary)

            result.summary = "\n".join(result_parts) if result_parts else "Aufgabe abgeschlossen."
            result.success = True

        except Exception as e:
            logger.error(f"[ClaudeBridge] Fehler bei Aufgabe: {e}", exc_info=True)
            result.success = False
            result.error = str(e)
            if on_progress:
                await on_progress(f"Fehler: {e}")

        return result

    async def get_project_status(self, project_id: str) -> str:
        """
        Fragt Claude nach dem aktuellen Projekt-Status.

        Nutzt eine kurze One-Shot-Query ohne Tool-Zugriff.
        """
        project_dir = self._get_project_dir(project_id)

        if not os.listdir(project_dir):
            return f"Projekt '{project_id}' ist leer. Noch keine Dateien vorhanden."

        resume_session = self._sessions.get(project_id)

        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep"],
            permission_mode="acceptEdits",
            cwd=project_dir,
            max_turns=5,
            system_prompt=(
                "Gib eine kurze Zusammenfassung des Projekts. "
                "Liste die wichtigsten Dateien und was sie tun. "
                "Halte dich kurz (max 3-4 Saetze), da dies per Sprache vorgelesen wird. "
                "Antworte auf Deutsch."
            ),
        )

        if resume_session:
            options.resume = resume_session

        result_parts = []

        try:
            async for message in query(
                prompt="Was ist der aktuelle Stand dieses Projekts?",
                options=options,
            ):
                if getattr(message, "type", None) == "result":
                    text = getattr(message, "result", "")
                    if text:
                        result_parts.append(text)
                elif getattr(message, "type", None) == "assistant":
                    content = getattr(message, "content", None)
                    if not content:
                        content = getattr(
                            getattr(message, "message", None), "content", []
                        )
                    for block in (content or []):
                        if hasattr(block, "text") and block.text:
                            result_parts.append(block.text)
        except Exception as e:
            logger.error(f"[ClaudeBridge] Status-Abfrage fehlgeschlagen: {e}")
            return f"Konnte Status nicht abrufen: {e}"

        return "\n".join(result_parts) if result_parts else "Keine Informationen verfuegbar."

    def clear_session(self, project_id: str):
        """Loescht die Session fuer ein Projekt."""
        self._sessions.pop(project_id, None)
