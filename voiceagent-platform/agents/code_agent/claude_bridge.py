"""
ClaudeCodingBridge - Wrapper um Claude CLI fuer den CodeAgent.

Fuehrt Coding-Aufgaben mit Claude CLI (MAX Account) aus:
- Code schreiben, lesen, editieren
- Bash-Befehle ausfuehren (Tests, Build, Git)
- Codebase navigieren und verstehen
- Sessions pro Projekt persistieren

Nutzt die Claude CLI als Subprocess statt des Agent SDK,
damit der MAX Account verwendet werden kann.
"""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from core.app.config import settings

logger = logging.getLogger(__name__)


def _get_claude_user_kwargs() -> dict:
    """Subprocess-kwargs um als non-root 'claude' User zu laufen.

    Claude CLI verweigert --dangerously-skip-permissions als root.
    Im Docker-Container gibt es den User 'claude', lokal (Windows) nicht.
    """
    try:
        import pwd
        pw = pwd.getpwnam("claude")
        env = os.environ.copy()
        env["HOME"] = pw.pw_dir
        return {"user": pw.pw_uid, "group": pw.pw_gid, "env": env}
    except (ImportError, KeyError):
        # Windows oder User existiert nicht (lokale Entwicklung)
        return {}


def _find_claude_cli() -> str:
    """Findet den Pfad zur Claude CLI."""
    path = shutil.which("claude")
    if path:
        return path
    # Typische Installationspfade pruefen
    for candidate in [
        os.path.expanduser("~/.claude/local/claude"),
        "/usr/local/bin/claude",
        os.path.expanduser("~/.npm-global/bin/claude"),
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        "Claude CLI nicht gefunden. Bitte installieren: npm install -g @anthropic-ai/claude-code"
    )


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
    Bridge zwischen VoiceAgent CodeAgent und Claude CLI.

    Ruft die Claude CLI als Subprocess auf (nutzt MAX Account Auth).
    Streamt JSON-Output fuer Progress-Updates.
    """

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self._sessions: dict[str, str] = {}  # project_id -> session_id
        self._claude_path = _find_claude_cli()
        logger.info(f"[ClaudeBridge] CLI gefunden: {self._claude_path}")

    def _get_project_dir(self, project_id: str) -> str:
        """Gibt das Arbeitsverzeichnis fuer ein Projekt zurueck."""
        project_dir = os.path.join(self.workspace_dir, project_id)
        os.makedirs(project_dir, exist_ok=True)
        # Sicherstellen, dass 'claude' User schreiben kann
        try:
            import pwd
            pw = pwd.getpwnam("claude")
            os.chown(project_dir, pw.pw_uid, pw.pw_gid)
        except (ImportError, KeyError, OSError):
            pass
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

    def _build_cli_args(
        self,
        project_dir: str,
        *,
        allowed_tools: Optional[list[str]] = None,
        max_turns: Optional[int] = None,
        system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
        output_format: str = "stream-json",
    ) -> list[str]:
        """Baut die CLI-Argumente fuer claude. Prompt wird via stdin uebergeben."""
        args = [
            self._claude_path,
            "--print",  # Non-interactive mode
            "--output-format", output_format,
            "--model", settings.CLAUDE_MODEL,
            "--dangerously-skip-permissions",  # Keine interaktiven Rueckfragen
            "--verbose",
        ]

        if max_turns:
            args.extend(["--max-turns", str(max_turns)])

        if system_prompt:
            args.extend(["--append-system-prompt", system_prompt])

        if session_id:
            args.extend(["--resume", session_id])

        if allowed_tools:
            # Komma-separiert uebergeben damit variadic flag nicht den Rest frisst
            args.extend(["--allowedTools", ",".join(allowed_tools)])

        return args

    async def execute_task(
        self,
        prompt: str,
        project_id: str,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        session_store=None,
    ) -> CodingResult:
        """
        Fuehrt eine Coding-Aufgabe mit Claude CLI aus.

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

        cli_args = self._build_cli_args(
            project_dir=project_dir,
            allowed_tools=settings.CLAUDE_ALLOWED_TOOLS,
            max_turns=settings.CLAUDE_MAX_TURNS,
            system_prompt=self._build_system_prompt(project_id),
            session_id=resume_session,
        )

        result = CodingResult()
        result_parts = []

        try:
            logger.info(f"[ClaudeBridge] Starte CLI: {' '.join(cli_args[:6])}...")

            process = await asyncio.create_subprocess_exec(
                *cli_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
                **_get_claude_user_kwargs(),
            )

            # Prompt via stdin senden
            process.stdin.write(prompt.encode("utf-8"))
            process.stdin.close()

            # Stream JSON-Output zeilenweise lesen
            async for line_bytes in process.stdout:
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Nicht-JSON-Output (z.B. Warnings) loggen
                    logger.debug(f"[ClaudeBridge] Non-JSON: {line[:200]}")
                    continue

                msg_type = event.get("type", "")

                if msg_type == "assistant":
                    # Text-Content extrahieren
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                result_parts.append(text)
                                if on_progress:
                                    await on_progress(text[:200])

                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            if tool_name:
                                result.tools_used.append(tool_name)
                                if on_progress:
                                    await on_progress(f"[Tool: {tool_name}]")

                            # Datei-Aenderungen tracken
                            tool_input = block.get("input", {})
                            if tool_name in ("Edit", "Write") and "file_path" in tool_input:
                                fpath = tool_input["file_path"]
                                if fpath not in result.files_changed:
                                    result.files_changed.append(fpath)

                elif msg_type == "result":
                    result_text = event.get("result", "")
                    if result_text:
                        result_parts.append(result_text)

                    # Session-ID speichern
                    sid = event.get("session_id")
                    if sid:
                        self._sessions[project_id] = sid
                        result.session_id = sid
                        if session_store:
                            summary = result_text[:200] if result_text else prompt[:200]
                            await session_store.save_session(project_id, sid, summary)

            # Auf Prozess-Ende warten
            await process.wait()

            if process.returncode != 0:
                stderr = await process.stderr.read()
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                if stderr_text and not result_parts:
                    logger.error(f"[ClaudeBridge] CLI stderr: {stderr_text}")
                    result.success = False
                    result.error = stderr_text[:500]
                    if on_progress:
                        await on_progress(f"Fehler: {stderr_text[:200]}")
                    return result

            result.summary = "\n".join(result_parts) if result_parts else "Aufgabe abgeschlossen."
            result.success = True

        except FileNotFoundError:
            msg = "Claude CLI nicht gefunden. Ist 'claude' installiert und im PATH?"
            logger.error(f"[ClaudeBridge] {msg}")
            result.success = False
            result.error = msg
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

        Nutzt eine kurze One-Shot-Query mit eingeschraenkten Tools.
        """
        project_dir = self._get_project_dir(project_id)

        if not os.listdir(project_dir):
            return f"Projekt '{project_id}' ist leer. Noch keine Dateien vorhanden."

        resume_session = self._sessions.get(project_id)

        system_prompt = (
            "Gib eine kurze Zusammenfassung des Projekts. "
            "Liste die wichtigsten Dateien und was sie tun. "
            "Halte dich kurz (max 3-4 Saetze), da dies per Sprache vorgelesen wird. "
            "Antworte auf Deutsch."
        )

        status_prompt = "Was ist der aktuelle Stand dieses Projekts?"

        cli_args = self._build_cli_args(
            project_dir=project_dir,
            allowed_tools=["Read", "Glob", "Grep"],
            max_turns=5,
            system_prompt=system_prompt,
            session_id=resume_session,
            output_format="json",  # Einfacher JSON-Output (kein Stream noetig)
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cli_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
                **_get_claude_user_kwargs(),
            )

            stdout, stderr = await process.communicate(input=status_prompt.encode("utf-8"))
            output = stdout.decode("utf-8", errors="replace").strip()

            if not output:
                if stderr:
                    logger.error(f"[ClaudeBridge] Status stderr: {stderr.decode()[:500]}")
                return "Konnte Status nicht abrufen."

            # JSON-Output parsen
            try:
                data = json.loads(output)
                # json format gibt result direkt zurueck
                result_text = data.get("result", "")
                if result_text:
                    return result_text
                # Fallback: Content-Blocks durchsuchen
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block.get("text", "")
            except json.JSONDecodeError:
                # Plaintext-Fallback
                return output[:500]

            return "Keine Informationen verfuegbar."

        except Exception as e:
            logger.error(f"[ClaudeBridge] Status-Abfrage fehlgeschlagen: {e}")
            return f"Konnte Status nicht abrufen: {e}"

    def clear_session(self, project_id: str):
        """Loescht die Session fuer ein Projekt."""
        self._sessions.pop(project_id, None)
