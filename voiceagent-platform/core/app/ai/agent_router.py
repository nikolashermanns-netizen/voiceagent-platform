"""
Agent Router - Erkennt Intents und routet zum passenden Agent.

Kann waehrend eines Anrufs den Agent wechseln basierend auf
dem Gespraechskontext.
"""

import logging
from typing import Optional

from core.app.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


class AgentRouter:
    """
    Intent-basiertes Routing zu Agenten.

    Analysiert Transkripte und erkennt wann ein Agent-Wechsel
    sinnvoll waere.
    """

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._conversation_history: list[dict] = []
        self._current_agent: Optional[str] = None

    def set_current_agent(self, agent_name: str):
        """Setzt den aktuellen Agent."""
        self._current_agent = agent_name

    def clear_history(self):
        """Loescht die Gespraecshistorie (z.B. bei neuem Anruf)."""
        self._conversation_history = []

    def add_transcript(self, role: str, text: str):
        """
        Fuegt ein Transkript-Segment hinzu.

        Args:
            role: 'caller' oder 'assistant'
            text: Transkript-Text
        """
        self._conversation_history.append({
            "role": role,
            "text": text
        })

        # Nur die letzten 20 Eintraege behalten
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-20:]

    def should_switch_agent(self, text: str) -> Optional[str]:
        """
        Prueft ob basierend auf dem Text ein Agent-Wechsel sinnvoll waere.

        Args:
            text: Neuer Transkript-Text

        Returns:
            Name des vorgeschlagenen Agents oder None
        """
        best_agent = self.registry.find_agent_for_intent(text)

        if best_agent and best_agent.name != self._current_agent:
            logger.info(
                f"Agent-Wechsel vorgeschlagen: {self._current_agent} -> {best_agent.name}"
            )
            return best_agent.name

        return None

    def get_context_summary(self) -> str:
        """
        Gibt eine Zusammenfassung des bisherigen Gespraechs zurueck.
        Nuetzlich fuer den Kontext-Transfer bei Agent-Wechsel.

        Returns:
            Zusammenfassung als Text
        """
        if not self._conversation_history:
            return ""

        lines = []
        for entry in self._conversation_history[-10:]:
            role = "Anrufer" if entry["role"] == "caller" else "Assistent"
            lines.append(f"{role}: {entry['text']}")

        return "\n".join(lines)
