"""
Haupt-Agent (Zentrale) fuer VoiceAgent Platform.

Begruesst Anrufer, erklaert Moeglichkeiten und leitet
zum passenden Fachagenten weiter.
"""

import logging
from typing import Optional

from core.app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

MAIN_AGENT_INSTRUCTIONS = """Du bist die Zentrale der VoiceAgent Plattform.

=== DEIN STIL ===
- Professionell, praezise und effizient
- Antworte IMMER so kurz wie moeglich - maximal 1-2 Saetze
- Wiederhole NIEMALS was der Anrufer gesagt hat
- Kein Geplaenkel, kein Fuelltext, kein Smalltalk
- Komm sofort zum Punkt

=== BEGRUESSUNG ===
"Hallo, Sie sind in der Zentrale."

=== WEITERLEITUNG ===
Wenn du erkennst wohin der Anrufer moechte:
- Sage kurz: "Alles klar, ich verbinde dich mit dem [Agent-Name]."
- Nutze dann SOFORT das Tool 'wechsel_zu_agent'
- Erkenne natuerliche Sprache: "Ich moechte programmieren" -> code_agent, "Ich habe eine Idee" -> ideas_agent

Wenn der Anrufer fragt was du kannst, nutze 'zeige_optionen' und stelle die Moeglichkeiten vor.

=== REGELN ===
- Halte Antworten ULTRA-KURZ (1-2 Saetze maximal)
- Wiederhole NICHT was der Anrufer gesagt hat - handle direkt
- Wenn unklar: Frage kurz und direkt nach
- KEIN Smalltalk - du bist eine effiziente Vermittlung
- Leite so schnell wie moeglich zum richtigen Agenten weiter"""


class MainAgent(BaseAgent):
    """Haupt-Agent der als Zentrale fungiert und zu Fachagenten weiterleitet."""

    def __init__(self):
        self._registry = None

    def set_registry(self, registry):
        """Setzt die AgentRegistry fuer dynamische Agent-Erkennung."""
        self._registry = registry

    @property
    def name(self) -> str:
        return "main_agent"

    @property
    def display_name(self) -> str:
        return "Zentrale"

    @property
    def description(self) -> str:
        return "Begruesst Anrufer und leitet zum passenden Fachagenten weiter."

    @property
    def capabilities(self) -> list[str]:
        return ["navigation", "weiterleitung", "uebersicht"]

    @property
    def keywords(self) -> list[str]:
        return [
            "zentrale", "hauptmenue", "menue", "zurueck", "optionen",
            "was kannst du", "hilfe", "help", "start",
        ]

    def _get_available_agents(self) -> list[dict]:
        """Gibt alle verfuegbaren Fachagenten zurueck (ohne sich selbst)."""
        if not self._registry:
            return []
        agents = []
        for agent in self._registry.get_all_agents():
            if agent.name not in ("main_agent", "security_agent"):
                agents.append({
                    "name": agent.name,
                    "display_name": agent.display_name,
                    "description": agent.description,
                })
        return agents

    def _get_agent_enum(self) -> list[str]:
        """Gibt die Agent-Namen als Liste fuer die Tool-Definition zurueck."""
        return [a["name"] for a in self._get_available_agents()]

    def get_tools(self) -> list[dict]:
        """OpenAI Realtime API Tool-Definitionen."""
        agent_names = self._get_agent_enum()
        tools = [
            {
                "type": "function",
                "name": "wechsel_zu_agent",
                "description": "Wechselt zum gewuenschten Fachagenten. Nutze dies sobald klar ist wohin der Anrufer moechte.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "enum": agent_names if agent_names else ["code_agent", "ideas_agent"],
                            "description": "Name des Ziel-Agenten"
                        }
                    },
                    "required": ["agent_name"]
                }
            },
            {
                "type": "function",
                "name": "zeige_optionen",
                "description": "Listet alle verfuegbaren Fachagenten mit Beschreibung auf. Nutze dies wenn der Anrufer fragt was es gibt.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
        ]
        return tools

    def get_instructions(self) -> str:
        """System-Prompt mit dynamischer Agent-Liste."""
        instructions = MAIN_AGENT_INSTRUCTIONS

        # Dynamische Agent-Liste anhaengen
        agents = self._get_available_agents()
        if agents:
            instructions += "\n\n=== VERFUEGBARE AGENTEN ==="
            for agent in agents:
                instructions += f"\n- {agent['display_name']} ({agent['name']}): {agent['description']}"

        return instructions

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Fuehrt ein Tool aus."""
        logger.info(f"[MainAgent] Tool: {tool_name}({arguments})")

        if tool_name == "wechsel_zu_agent":
            return self._wechsel_zu_agent(arguments)
        elif tool_name == "zeige_optionen":
            return self._zeige_optionen()
        else:
            return f"Unbekannte Funktion: {tool_name}"

    def _wechsel_zu_agent(self, args: dict) -> str:
        """Gibt Switch-Signal zurueck das von main.py verarbeitet wird."""
        agent_name = args.get("agent_name", "")
        if not agent_name:
            return "Fehler: Kein Agent angegeben."

        # Pruefen ob Agent existiert
        if self._registry:
            agent = self._registry.get_agent(agent_name)
            if not agent:
                available = ", ".join(self._get_agent_enum())
                return f"Agent '{agent_name}' nicht gefunden. Verfuegbar: {available}"

        # Switch-Signal fuer main.py
        return f"__SWITCH__:{agent_name}"

    def _zeige_optionen(self) -> str:
        """Listet alle verfuegbaren Agenten auf."""
        agents = self._get_available_agents()
        if not agents:
            return "Aktuell sind keine Fachagenten verfuegbar."

        lines = [f"=== {len(agents)} Fachagenten verfuegbar ===\n"]
        for agent in agents:
            lines.append(f"- {agent['display_name']}: {agent['description']}")

        lines.append("\nSage einfach den Namen des Agenten um dich verbinden zu lassen.")
        return "\n".join(lines)


def create_agent() -> BaseAgent:
    """Factory-Funktion fuer Agent-Discovery."""
    return MainAgent()
