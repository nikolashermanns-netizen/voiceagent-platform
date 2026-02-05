"""
Code-Agent fuer VoiceAgent Platform.

Kann per Sprache Code schreiben und in einer Docker-Sandbox ausfuehren.
Unterstuetzt Python, JavaScript und Bash.
"""

import logging
from typing import Optional

from core.app.agents.base import BaseAgent
from agents.code_agent.sandbox import CodeSandbox
from agents.code_agent.project_manager import ProjectManager

logger = logging.getLogger(__name__)

CODE_AGENT_INSTRUCTIONS = """Du bist ein Programmier-Assistent der per Telefon Code schreiben und ausfuehren kann.

=== DEIN STIL ===
- Sei freundlich und hilfsbereit
- Erklaere was du tust, kurz und verstaendlich
- Benutze einfache Sprache, keine ueberfluessigen Fachbegriffe

=== DEINE FAEHIGKEITEN ===
1. CODE SCHREIBEN: Du kannst Python, JavaScript und Bash Code schreiben
2. CODE AUSFUEHREN: Code wird sicher in einer Sandbox ausgefuehrt
3. DATEIEN VERWALTEN: Dateien im Projekt erstellen und anzeigen

=== ABLAUF ===
1. Hoere was der Benutzer will
2. Schreibe den Code mit 'code_schreiben'
3. Fuehre ihn aus mit 'code_ausfuehren'
4. Erklaere das Ergebnis

=== SICHERHEIT ===
- Code laeuft in isolierter Sandbox (kein Netzwerk)
- Timeout nach 5 Minuten
- Nur Python, JavaScript, Bash

=== REGELN ===
- Erklaere Ergebnisse kurz und verstaendlich (fuer Sprachausgabe!)
- Bei Fehlern: Erklaere was schief ging und frage ob du es fixen sollst
- Halte Code einfach und lesbar
- Frage bei Unklarheiten nach"""


class CodeAgent(BaseAgent):
    """Agent fuer Code-Erstellung und -Ausfuehrung."""

    def __init__(self):
        self._sandbox = CodeSandbox()
        self._project_manager = ProjectManager()
        self._current_project = "default"

    @property
    def name(self) -> str:
        return "code_agent"

    @property
    def display_name(self) -> str:
        return "Programmier-Assistent"

    @property
    def description(self) -> str:
        return "Schreibt und fuehrt Code aus per Sprache. Python, JavaScript, Bash in sicherer Sandbox."

    @property
    def capabilities(self) -> list[str]:
        return ["programmieren", "code", "script", "automatisierung", "berechnung"]

    @property
    def keywords(self) -> list[str]:
        return [
            "programmieren", "code", "python", "javascript", "script",
            "berechne", "rechne", "programm", "funktion", "algorithmus",
            "automatisiere", "skript", "bash",
        ]

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "code_schreiben",
                "description": "Schreibt Code in eine Datei im Projekt. Der Code kann danach ausgefuehrt werden.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dateiname": {
                            "type": "string",
                            "description": "Name der Datei (z.B. 'main.py', 'script.js')"
                        },
                        "code": {
                            "type": "string",
                            "description": "Der Code der geschrieben werden soll"
                        },
                        "sprache": {
                            "type": "string",
                            "enum": ["python", "javascript", "bash"],
                            "description": "Programmiersprache"
                        }
                    },
                    "required": ["dateiname", "code", "sprache"]
                }
            },
            {
                "type": "function",
                "name": "code_ausfuehren",
                "description": "Fuehrt Code sicher in einer Sandbox aus.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Der auszufuehrende Code"
                        },
                        "sprache": {
                            "type": "string",
                            "enum": ["python", "javascript", "bash"],
                            "description": "Programmiersprache"
                        }
                    },
                    "required": ["code", "sprache"]
                }
            },
            {
                "type": "function",
                "name": "dateien_zeigen",
                "description": "Zeigt alle Dateien im aktuellen Projekt.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "datei_lesen",
                "description": "Liest den Inhalt einer Datei im Projekt.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dateiname": {
                            "type": "string",
                            "description": "Name der Datei"
                        }
                    },
                    "required": ["dateiname"]
                }
            },
        ]

    def get_instructions(self) -> str:
        return CODE_AGENT_INSTRUCTIONS

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        logger.info(f"[CodeAgent] Tool: {tool_name}")

        if tool_name == "code_schreiben":
            return await self._code_schreiben(arguments)
        elif tool_name == "code_ausfuehren":
            return await self._code_ausfuehren(arguments)
        elif tool_name == "dateien_zeigen":
            return self._dateien_zeigen()
        elif tool_name == "datei_lesen":
            return self._datei_lesen(arguments)
        else:
            return f"Unbekannte Funktion: {tool_name}"

    async def _code_schreiben(self, args: dict) -> str:
        dateiname = args.get("dateiname", "main.py")
        code = args.get("code", "")
        sprache = args.get("sprache", "python")

        if not code:
            return "Fehler: Kein Code angegeben."

        success = self._project_manager.write_file(
            self._current_project, dateiname, code
        )

        if success:
            return f"Datei '{dateiname}' geschrieben ({len(code)} Zeichen, {sprache})."
        return f"Fehler beim Schreiben von '{dateiname}'."

    async def _code_ausfuehren(self, args: dict) -> str:
        code = args.get("code", "")
        sprache = args.get("sprache", "python")

        if not code:
            return "Fehler: Kein Code angegeben."

        result = await self._sandbox.execute(
            code=code, language=sprache, project_id=self._current_project
        )

        return result.to_string()

    def _dateien_zeigen(self) -> str:
        files = self._project_manager.list_files(self._current_project)
        if not files:
            return "Keine Dateien im Projekt."

        lines = [f"=== Dateien im Projekt '{self._current_project}' ==="]
        for f in files:
            lines.append(f"  - {f}")
        return "\n".join(lines)

    def _datei_lesen(self, args: dict) -> str:
        dateiname = args.get("dateiname", "")
        if not dateiname:
            return "Fehler: Kein Dateiname angegeben."

        content = self._project_manager.read_file(self._current_project, dateiname)
        if content is None:
            return f"Datei '{dateiname}' nicht gefunden."

        return f"=== {dateiname} ===\n{content}"


def create_agent() -> BaseAgent:
    """Factory-Funktion fuer Agent-Discovery."""
    return CodeAgent()
