"""
BaseAgent - Abstrakte Basisklasse fuer alle Agenten.

Jeder Agent implementiert diese Klasse und stellt
Tools, Instructions und Tool-Ausfuehrung bereit.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from core.app.tasks.models import Task

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstrakte Basisklasse fuer VoiceAgent-Agenten.

    Jeder Agent muss mindestens implementieren:
    - name: Eindeutiger Identifier
    - display_name: Anzeigename
    - description: Kurzbeschreibung
    - get_tools(): OpenAI Function-Calling Tool-Definitionen
    - get_instructions(): System-Prompt fuer die AI
    - execute_tool(): Tool-Ausfuehrung bei Function Call
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Agent-Name (z.B. 'bestell_agent')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Anzeigename (z.B. 'Bestell-Service')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Kurzbeschreibung der Agent-Funktion."""
        ...

    @property
    def capabilities(self) -> list[str]:
        """Liste der Faehigkeiten fuer Intent-Routing."""
        return []

    @property
    def keywords(self) -> list[str]:
        """Schluesselwoerter fuer Intent-Erkennung."""
        return []

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """
        Gibt die OpenAI Function-Calling Tool-Definitionen zurueck.

        Returns:
            Liste von Tool-Dicts im OpenAI Realtime API Format:
            [{"type": "function", "name": "...", "description": "...", "parameters": {...}}]
        """
        ...

    @abstractmethod
    def get_instructions(self) -> str:
        """
        Gibt den System-Prompt fuer diesen Agent zurueck.

        Returns:
            Vollstaendige Instructions fuer die OpenAI Realtime Session
        """
        ...

    @abstractmethod
    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Fuehrt ein Tool aus und gibt das Ergebnis zurueck.

        Args:
            tool_name: Name der aufgerufenen Funktion
            arguments: Argumente als Dict

        Returns:
            Ergebnis als String fuer den AI-Kontext
        """
        ...

    async def on_call_start(self, caller_id: str):
        """
        Wird aufgerufen wenn ein neuer Anruf beginnt.
        Optional zu ueberschreiben fuer Setup-Logik.

        Args:
            caller_id: SIP Caller-ID
        """
        logger.info(f"[{self.name}] Call gestartet: {caller_id}")

    async def on_call_end(self, caller_id: str):
        """
        Wird aufgerufen wenn ein Anruf endet.
        Optional zu ueberschreiben fuer Cleanup-Logik.

        Args:
            caller_id: SIP Caller-ID
        """
        logger.info(f"[{self.name}] Call beendet: {caller_id}")

    async def on_agent_activated(self):
        """Wird aufgerufen wenn dieser Agent aktiviert wird (z.B. bei Wechsel)."""
        logger.info(f"[{self.name}] Agent aktiviert")

    async def on_agent_deactivated(self):
        """Wird aufgerufen wenn dieser Agent deaktiviert wird."""
        logger.info(f"[{self.name}] Agent deaktiviert")

    def matches_intent(self, text: str) -> float:
        """
        Prueft ob ein Text zu diesem Agent passt (Intent-Erkennung).

        Args:
            text: Eingabetext (z.B. Transkript)

        Returns:
            Score 0.0-1.0 wie gut der Text zum Agent passt
        """
        text_lower = text.lower()
        score = 0.0

        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                score += 0.3

        return min(score, 1.0)

    def __repr__(self) -> str:
        return f"<Agent:{self.name} ({self.display_name})>"
