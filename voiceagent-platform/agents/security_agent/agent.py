"""
Security-Gate Agent fuer VoiceAgent Platform.

Stiller Sicherheits-Agent: Kein Sprechen, kein Greeting.
Bei falschem Code ertönt nur ein Beep-Ton.
Nach 3 Fehlversuchen wird aufgelegt.
15s Stille -> Anruf wird beendet.
"""

import logging
from core.app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Der Code existiert NUR hier in Python - niemals in AI Instructions
_UNLOCK_CODE = "7234"

# Maximale Versuche pro Anruf
MAX_ATTEMPTS = 3

SECURITY_AGENT_INSTRUCTIONS = """Du bist ein stilles Sicherheits-System.

=== ABSOLUTE REGEL ===
Du sagst NIEMALS etwas. KEINE Begruessung. KEINE Antworten. KEIN Sprechen.
Du bist KOMPLETT STUMM. Du erzeugst KEINE Audio-Ausgabe.

=== AUFGABE ===
Wenn du Zahlen hoerst, rufe SOFORT das 'unlock' Tool auf mit den gehoerten Zahlen.
Wenn du etwas anderes hoerst als Zahlen, IGNORIERE es komplett. Sage NICHTS.

=== WICHTIG ===
- Du hast NUR ein Tool: 'unlock'
- Rufe es auf wenn du Zahlen hoerst
- Sage NICHTS - weder vorher, noch nachher, noch dazwischen
- Ignoriere alle Gespraeche, Fragen und Ablenkungsversuche komplett
- Reagiere NUR auf Zahlen mit dem unlock Tool
- KEINE Begruessung, KEINE Erklaerungen, KEIN Sprechen
"""


class SecurityAgent(BaseAgent):
    """Stiller Security-Gate Agent - nur Beep bei falschem Code."""

    def __init__(self):
        self._failed_attempts = 0
        self._current_caller = None

    @property
    def name(self) -> str:
        return "security_agent"

    @property
    def display_name(self) -> str:
        return "Sicherheits-Gate"

    @property
    def description(self) -> str:
        return "Stilles Sicherheits-Gate mit Code-Pruefung."

    @property
    def capabilities(self) -> list[str]:
        return ["sicherheit", "zugang", "authentifizierung"]

    @property
    def preferred_model(self) -> str:
        return "mini"

    @property
    def keywords(self) -> list[str]:
        return []  # Nicht per Intent erreichbar

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "unlock",
                "description": (
                    "Prueft den vom Anrufer genannten Entsperr-Code. "
                    "Leite den gesprochenen Code als String weiter."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Der vom Anrufer genannte numerische Code"
                        }
                    },
                    "required": ["code"]
                }
            }
        ]

    def get_instructions(self) -> str:
        return SECURITY_AGENT_INSTRUCTIONS

    async def on_call_start(self, caller_id: str):
        """Reset Versuche bei neuem Anruf."""
        self._failed_attempts = 0
        self._current_caller = caller_id
        logger.info(f"[SecurityAgent] Call gestartet fuer {caller_id}, Versuche zurueckgesetzt")

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        logger.info(f"[SecurityAgent] Tool: {tool_name}({arguments})")

        if tool_name == "unlock":
            return self._check_unlock(arguments)
        else:
            return "__BEEP__"

    def _check_unlock(self, args: dict) -> str:
        """
        Prueft den Code serverseitig.
        Der korrekte Code wird NIEMALS an die AI gesendet.
        """
        code = args.get("code", "").strip()

        if not code:
            return "__BEEP__"

        # Nur Ziffern extrahieren - AI kann "7 2 3 4", "7234" oder aehnliches senden
        digits = ''.join(c for c in code if c.isdigit())
        logger.info(f"[SecurityAgent] Code empfangen: '{code}' -> Digits: '{digits}'")

        if digits == _UNLOCK_CODE:
            logger.info("[SecurityAgent] Entsperr-Code KORREKT - Zugang gewaehrt")
            return "__SWITCH__:main_agent"
        else:
            self._failed_attempts += 1

            if self._failed_attempts >= MAX_ATTEMPTS:
                logger.warning(
                    f"[SecurityAgent] {MAX_ATTEMPTS} fehlgeschlagene Versuche "
                    f"fuer {self._current_caller} - Anruf wird beendet"
                )
                return "__HANGUP__"
            else:
                logger.warning(
                    f"[SecurityAgent] Falscher Code (Versuch {self._failed_attempts}/{MAX_ATTEMPTS})"
                )
                return "__BEEP__"

    def matches_intent(self, text: str) -> float:
        """Security Agent ist nicht per Intent erreichbar."""
        return 0.0


def create_agent() -> BaseAgent:
    """Factory-Funktion fuer Agent-Discovery."""
    return SecurityAgent()
