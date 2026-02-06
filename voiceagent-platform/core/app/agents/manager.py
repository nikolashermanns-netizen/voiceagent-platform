"""
AgentManager - Verwaltet den aktiven Agent pro Anruf.

Kuemmert sich um Agent-Lifecycle, Wechsel waehrend eines Calls
und Kontext-Verwaltung.
"""

import logging
from typing import Callable, Optional

from core.app.agents.base import BaseAgent
from core.app.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


_AUFLEGEN_TOOL = {
    "type": "function",
    "name": "auflegen",
    "description": "Beendet das Telefonat. Verwende dieses Tool wenn der Anrufer auflegen moechte, sich verabschiedet oder sagt 'leg auf', 'tschuess', 'auf wiedersehen'.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

_MODEL_WECHSELN_TOOL = {
    "type": "function",
    "name": "model_wechseln",
    "description": (
        "Wechselt das AI-Modell. Verwende wenn der Anrufer "
        "'model thinking', 'model premium', 'model teuer' oder "
        "'model schnell', 'model guenstig', 'model mini', 'model cheap' sagt."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "enum": ["mini", "premium"],
                "description": "mini = guenstig/schnell, premium = teuer/thinking"
            }
        },
        "required": ["model"],
    },
}


class AgentManager:
    """
    Verwaltet den aktiven Agent waehrend eines Anrufs.

    Pro Anruf ist immer genau ein Agent aktiv.
    Der Agent kann waehrend des Anrufs gewechselt werden.
    """

    def __init__(self, registry: AgentRegistry, default_agent: str = None):
        self.registry = registry
        self._default_agent_name = default_agent
        self._active_agent: Optional[BaseAgent] = None
        self._current_caller: Optional[str] = None
        self._call_context: dict = {}

        # Security Gate: Anruf ist erst nach erfolgreichem Unlock freigeschaltet
        self._call_unlocked: bool = False

        # Callback wenn Agent gewechselt wird
        self.on_agent_changed: Optional[Callable[[str, str], None]] = None

    @property
    def active_agent(self) -> Optional[BaseAgent]:
        """Aktuell aktiver Agent."""
        return self._active_agent

    @property
    def active_agent_name(self) -> Optional[str]:
        """Name des aktiven Agents."""
        return self._active_agent.name if self._active_agent else None

    @property
    def is_in_call(self) -> bool:
        """Ist ein Anruf aktiv?"""
        return self._current_caller is not None

    @property
    def call_unlocked(self) -> bool:
        """Ist der aktuelle Anruf entsperrt?"""
        return self._call_unlocked

    def set_call_unlocked(self, unlocked: bool = True):
        """Setzt den Unlock-Status fuer den aktuellen Anruf."""
        self._call_unlocked = unlocked
        logger.info(f"Call unlock status: {unlocked}")

    async def start_call(self, caller_id: str, agent_name: str = None):
        """
        Startet einen neuen Anruf und aktiviert den passenden Agent.

        Args:
            caller_id: SIP Caller-ID
            agent_name: Optionaler Agent-Name (sonst Default)
        """
        self._current_caller = caller_id
        self._call_context = {"caller_id": caller_id}
        self._call_unlocked = False  # Security Gate: Jeder neue Anruf startet gesperrt

        # Agent waehlen
        target_name = agent_name or self._default_agent_name
        if target_name:
            agent = self.registry.get_agent(target_name)
        else:
            # Erster verfuegbarer Agent
            agents = self.registry.get_all_agents()
            agent = agents[0] if agents else None

        if agent:
            self._active_agent = agent
            await agent.on_call_start(caller_id)
            await agent.on_agent_activated()
            logger.info(f"Call gestartet: {caller_id} -> Agent: {agent.name}")
        else:
            logger.error(f"Kein Agent verfuegbar fuer Call von {caller_id}")

    async def end_call(self):
        """Beendet den aktuellen Anruf und deaktiviert den Agent."""
        if self._active_agent and self._current_caller:
            await self._active_agent.on_call_end(self._current_caller)
            await self._active_agent.on_agent_deactivated()
            logger.info(
                f"Call beendet: {self._current_caller} (Agent: {self._active_agent.name})"
            )

        self._active_agent = None
        self._current_caller = None
        self._call_context = {}
        self._call_unlocked = False  # Security Gate: Bei Anrufende zuruecksetzen

    async def switch_agent(self, agent_name: str) -> bool:
        """
        Wechselt den aktiven Agent waehrend eines Anrufs.

        Args:
            agent_name: Name des neuen Agents

        Returns:
            True wenn erfolgreich gewechselt
        """
        new_agent = self.registry.get_agent(agent_name)
        if not new_agent:
            logger.warning(f"Agent '{agent_name}' nicht gefunden")
            return False

        if self._active_agent and self._active_agent.name == agent_name:
            logger.info(f"Agent '{agent_name}' ist bereits aktiv")
            return True

        old_name = self._active_agent.name if self._active_agent else "none"

        # Alten Agent deaktivieren
        if self._active_agent:
            await self._active_agent.on_agent_deactivated()

        # Neuen Agent aktivieren
        self._active_agent = new_agent
        await new_agent.on_agent_activated()

        if self._current_caller:
            await new_agent.on_call_start(self._current_caller)

        logger.info(f"Agent gewechselt: {old_name} -> {agent_name}")

        # Callback
        if self.on_agent_changed:
            try:
                await self.on_agent_changed(old_name, agent_name)
            except Exception as e:
                logger.warning(f"on_agent_changed callback error: {e}")

        return True

    def get_tools(self) -> list[dict]:
        """Gibt die Tools des aktiven Agents zurueck (inkl. globale Tools)."""
        if self._active_agent:
            tools = self._active_agent.get_tools() + [_AUFLEGEN_TOOL]
            # Model-Wechsel nur fuer Agents ohne erzwungenes Modell
            if not self._active_agent.preferred_model:
                tools.append(_MODEL_WECHSELN_TOOL)
            return tools
        return []

    def get_instructions(self) -> str:
        """Gibt die Instructions des aktiven Agents zurueck."""
        if self._active_agent:
            return self._active_agent.get_instructions()
        return ""

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Fuehrt ein Tool des aktiven Agents aus.

        Args:
            tool_name: Name der Funktion
            arguments: Argumente als Dict

        Returns:
            Ergebnis als String
        """
        if not self._active_agent:
            return "Fehler: Kein Agent aktiv."

        # Globales Tool: Auflegen (funktioniert in jedem Agent, auch Security)
        if tool_name == "auflegen":
            logger.info("Benutzer moechte auflegen (Auflegen-Tool)")
            return "__HANGUP_USER__"

        # Globales Tool: Model wechseln
        if tool_name == "model_wechseln":
            model = arguments.get("model", "mini")
            logger.info(f"Model-Wechsel angefordert: {model}")
            return f"__MODEL_SWITCH__:{model}"

        # Security Gate: Wenn Anruf nicht entsperrt, nur security_agent Tools erlauben
        if not self._call_unlocked and self._active_agent.name != "security_agent":
            logger.warning(f"Tool '{tool_name}' blockiert - Anruf nicht entsperrt")
            return "Fehler: Anruf nicht freigeschaltet. Bitte zuerst den Zugangs-Code eingeben."

        try:
            return await self._active_agent.execute_tool(tool_name, arguments)
        except Exception as e:
            logger.error(f"Tool-Ausfuehrung fehlgeschlagen: {tool_name} - {e}")
            return f"Fehler bei {tool_name}: {e}"

    async def route_by_intent(self, text: str) -> bool:
        """
        Versucht anhand eines Texts den passenden Agent zu finden und zu wechseln.

        Args:
            text: Eingabetext fuer Intent-Erkennung

        Returns:
            True wenn ein Agent-Wechsel stattgefunden hat
        """
        best_agent = self.registry.find_agent_for_intent(text)

        if best_agent and (
            not self._active_agent or best_agent.name != self._active_agent.name
        ):
            return await self.switch_agent(best_agent.name)

        return False
