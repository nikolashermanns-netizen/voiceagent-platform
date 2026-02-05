"""
AgentRegistry - Verwaltet alle verfuegbaren Agenten.

Bietet Registration, Lookup und Intent-basiertes Routing.
"""

import importlib
import logging
import os
from typing import Optional

from core.app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Registry fuer alle verfuegbaren Agenten.

    Agenten koennen manuell registriert oder automatisch
    aus dem agents/ Verzeichnis entdeckt werden.
    """

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        """
        Registriert einen Agent in der Registry.

        Args:
            agent: BaseAgent-Instanz
        """
        if agent.name in self._agents:
            logger.warning(f"Agent '{agent.name}' wird ueberschrieben")

        self._agents[agent.name] = agent
        logger.info(f"Agent registriert: {agent.name} ({agent.display_name})")

    def unregister(self, agent_name: str):
        """Entfernt einen Agent aus der Registry."""
        if agent_name in self._agents:
            del self._agents[agent_name]
            logger.info(f"Agent entfernt: {agent_name}")

    def get_agent(self, agent_name: str) -> Optional[BaseAgent]:
        """
        Gibt einen Agent nach Name zurueck.

        Args:
            agent_name: Eindeutiger Agent-Name

        Returns:
            BaseAgent-Instanz oder None
        """
        return self._agents.get(agent_name)

    def get_all_agents(self) -> list[BaseAgent]:
        """Gibt alle registrierten Agenten zurueck."""
        return list(self._agents.values())

    def get_agent_names(self) -> list[str]:
        """Gibt alle registrierten Agent-Namen zurueck."""
        return list(self._agents.keys())

    def get_agent_info(self) -> list[dict]:
        """Gibt Info ueber alle Agenten zurueck (fuer API/GUI)."""
        return [
            {
                "name": agent.name,
                "display_name": agent.display_name,
                "description": agent.description,
                "capabilities": agent.capabilities,
                "tools_count": len(agent.get_tools()),
            }
            for agent in self._agents.values()
        ]

    def find_agent_for_intent(self, text: str) -> Optional[BaseAgent]:
        """
        Findet den besten Agent fuer einen gegebenen Intent-Text.

        Args:
            text: Eingabetext (z.B. Transkript oder Benutzeranfrage)

        Returns:
            Bester Agent oder None wenn kein Agent passt
        """
        best_agent = None
        best_score = 0.0

        for agent in self._agents.values():
            score = agent.matches_intent(text)
            if score > best_score:
                best_score = score
                best_agent = agent

        if best_agent and best_score > 0.0:
            logger.info(
                f"Intent-Routing: '{text[:50]}...' -> {best_agent.name} (score={best_score:.2f})"
            )
            return best_agent

        return None

    def discover_agents(self, agents_dir: str):
        """
        Entdeckt und laedt Agenten aus einem Verzeichnis.

        Erwartet in jedem Unterordner eine agent.py mit einer
        Klasse die BaseAgent implementiert und eine create_agent() Funktion.

        Args:
            agents_dir: Pfad zum agents/ Verzeichnis
        """
        if not os.path.isdir(agents_dir):
            logger.warning(f"Agents-Verzeichnis nicht gefunden: {agents_dir}")
            return

        for entry in os.listdir(agents_dir):
            agent_path = os.path.join(agents_dir, entry)

            if not os.path.isdir(agent_path):
                continue

            agent_file = os.path.join(agent_path, "agent.py")
            if not os.path.exists(agent_file):
                continue

            try:
                # Modul dynamisch laden
                module_name = f"agents.{entry}.agent"
                spec = importlib.util.spec_from_file_location(module_name, agent_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # create_agent() Funktion aufrufen
                if hasattr(module, "create_agent"):
                    agent = module.create_agent()
                    if isinstance(agent, BaseAgent):
                        self.register(agent)
                    else:
                        logger.warning(
                            f"create_agent() in {entry} gibt keinen BaseAgent zurueck"
                        )
                else:
                    logger.warning(f"Keine create_agent() Funktion in {entry}/agent.py")

            except Exception as e:
                logger.error(f"Fehler beim Laden von Agent '{entry}': {e}")

    @property
    def count(self) -> int:
        """Anzahl registrierter Agenten."""
        return len(self._agents)
