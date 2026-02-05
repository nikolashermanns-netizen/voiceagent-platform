"""
Ideen-Agent fuer VoiceAgent Platform.

Erfasst Ideen per Sprache, verwaltet sie und erstellt Projekte daraus.
"""

import logging
from typing import Optional

from core.app.agents.base import BaseAgent
from core.app.db.database import get_database
from agents.ideas_agent.idea_store import IdeaStore, Idea
from agents.ideas_agent.project_planner import ProjectPlanner, Project

logger = logging.getLogger(__name__)

IDEAS_AGENT_INSTRUCTIONS = """Du bist ein Ideen-Assistent der per Telefon Ideen erfasst und verwaltet.

=== DEIN STIL ===
- Sei begeistert und motivierend
- Zeige echtes Interesse an den Ideen
- Helfe beim Strukturieren und Weiterdenken

=== DEINE FAEHIGKEITEN ===
1. IDEEN ERFASSEN: Neue Ideen aufnehmen mit Titel und Beschreibung
2. IDEEN ANZEIGEN: Bestehende Ideen auflisten
3. PROJEKTE ERSTELLEN: Aus Ideen ein Projekt planen
4. PROJEKT-STATUS: Stand eines Projekts abfragen

=== ABLAUF ===
1. Hoere die Idee des Benutzers
2. Fasse sie kurz zusammen und frage ob das stimmt
3. Erfasse sie mit 'idee_erfassen'
4. Frage ob noch etwas dazugehoert oder ob es alles war

=== KATEGORIEN ===
Ordne Ideen automatisch einer Kategorie zu:
- software: Programmierung, Apps, Webseiten
- business: Geschaeftsideen, Produkte
- automation: Automatisierung, Prozesse
- kreativ: Design, Medien, Kunst
- sonstiges: Alles andere

=== REGELN ===
- Kurze Antworten (fuer Sprachausgabe!)
- Wiederhole die Idee kurz zur Bestaetigung
- Frage bei Unklarheiten nach
- Sei positiv und ermutigend

=== ZURUECK ZUR ZENTRALE ===
Wenn der Anrufer "exit", "zurueck", "menue" oder "hauptmenue" sagt:
- Sage kurz: "Alles klar, ich bringe dich zurueck zur Zentrale."
- Nutze dann SOFORT das Tool 'zurueck_zur_zentrale'"""


class IdeasAgent(BaseAgent):
    """Agent fuer Ideen-Erfassung und Projektverwaltung."""

    def __init__(self):
        self._idea_store: Optional[IdeaStore] = None
        self._project_planner: Optional[ProjectPlanner] = None

    async def _ensure_stores(self):
        """Stellt sicher dass die Stores initialisiert sind."""
        if self._idea_store is None:
            db = await get_database()
            self._idea_store = IdeaStore(db)
            self._project_planner = ProjectPlanner(db)

    @property
    def name(self) -> str:
        return "ideas_agent"

    @property
    def display_name(self) -> str:
        return "Ideen-Assistent"

    @property
    def description(self) -> str:
        return "Erfasst Ideen per Sprache, verwaltet sie und erstellt Projekte daraus."

    @property
    def capabilities(self) -> list[str]:
        return ["ideen", "notizen", "projekte", "brainstorming", "planung"]

    @property
    def keywords(self) -> list[str]:
        return [
            "idee", "ideen", "einfall", "gedanke", "notiz", "notizen",
            "projekt", "plan", "brainstorming", "aufschreiben",
            "merken", "festhalten", "vorschlag",
        ]

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "idee_erfassen",
                "description": "Erfasst eine neue Idee.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "titel": {
                            "type": "string",
                            "description": "Kurzer Titel der Idee"
                        },
                        "beschreibung": {
                            "type": "string",
                            "description": "Ausfuehrliche Beschreibung"
                        },
                        "kategorie": {
                            "type": "string",
                            "enum": ["software", "business", "automation", "kreativ", "sonstiges"],
                            "description": "Kategorie der Idee"
                        }
                    },
                    "required": ["titel", "beschreibung", "kategorie"]
                }
            },
            {
                "type": "function",
                "name": "ideen_zeigen",
                "description": "Zeigt alle gespeicherten Ideen an.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kategorie": {
                            "type": "string",
                            "enum": ["software", "business", "automation", "kreativ", "sonstiges"],
                            "description": "Optional: Nur Ideen dieser Kategorie"
                        }
                    },
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "notiz_hinzufuegen",
                "description": "Fuegt eine Notiz zu einer bestehenden Idee hinzu.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "idee_id": {
                            "type": "string",
                            "description": "ID der Idee"
                        },
                        "notiz": {
                            "type": "string",
                            "description": "Die Notiz"
                        }
                    },
                    "required": ["idee_id", "notiz"]
                }
            },
            {
                "type": "function",
                "name": "projekt_erstellen",
                "description": "Erstellt ein neues Projekt aus einer oder mehreren Ideen.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "titel": {
                            "type": "string",
                            "description": "Projekttitel"
                        },
                        "beschreibung": {
                            "type": "string",
                            "description": "Projektbeschreibung"
                        },
                        "ideen_ids": {
                            "type": "string",
                            "description": "Komma-getrennte Ideen-IDs fuer das Projekt"
                        }
                    },
                    "required": ["titel", "beschreibung"]
                }
            },
            {
                "type": "function",
                "name": "projekte_zeigen",
                "description": "Zeigt alle Projekte an.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
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
                    "required": []
                }
            },
        ]

    def get_instructions(self) -> str:
        return IDEAS_AGENT_INSTRUCTIONS

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        await self._ensure_stores()
        logger.info(f"[IdeasAgent] Tool: {tool_name}")

        if tool_name == "idee_erfassen":
            return await self._idee_erfassen(arguments)
        elif tool_name == "ideen_zeigen":
            return await self._ideen_zeigen(arguments)
        elif tool_name == "notiz_hinzufuegen":
            return await self._notiz_hinzufuegen(arguments)
        elif tool_name == "projekt_erstellen":
            return await self._projekt_erstellen(arguments)
        elif tool_name == "projekte_zeigen":
            return await self._projekte_zeigen()
        elif tool_name == "zurueck_zur_zentrale":
            return "__SWITCH__:main_agent"
        else:
            return f"Unbekannte Funktion: {tool_name}"

    async def _idee_erfassen(self, args: dict) -> str:
        titel = args.get("titel", "")
        beschreibung = args.get("beschreibung", "")
        kategorie = args.get("kategorie", "sonstiges")

        if not titel:
            return "Fehler: Kein Titel angegeben."

        idea = Idea(
            title=titel,
            description=beschreibung,
            category=kategorie,
        )
        await self._idea_store.create(idea)

        return f"Idee erfasst! ID: {idea.id}, Titel: '{titel}', Kategorie: {kategorie}"

    async def _ideen_zeigen(self, args: dict) -> str:
        kategorie = args.get("kategorie")
        ideas = await self._idea_store.get_all(category=kategorie)

        if not ideas:
            msg = "Noch keine Ideen gespeichert."
            if kategorie:
                msg = f"Keine Ideen in Kategorie '{kategorie}'."
            return msg

        lines = [f"=== {len(ideas)} Ideen ===\n"]
        for idea in ideas[:20]:
            lines.append(
                f"[{idea.id}] {idea.title} ({idea.category}) - {idea.status}"
            )
            if idea.description:
                lines.append(f"     {idea.description[:100]}")

        if len(ideas) > 20:
            lines.append(f"\n... und {len(ideas) - 20} weitere")

        return "\n".join(lines)

    async def _notiz_hinzufuegen(self, args: dict) -> str:
        idee_id = args.get("idee_id", "")
        notiz = args.get("notiz", "")

        if not idee_id or not notiz:
            return "Fehler: Idee-ID und Notiz benoetigt."

        idea = await self._idea_store.add_note(idee_id, notiz)
        if not idea:
            return f"Idee '{idee_id}' nicht gefunden."

        return f"Notiz hinzugefuegt zu '{idea.title}'. Jetzt {len(idea.notes)} Notizen."

    async def _projekt_erstellen(self, args: dict) -> str:
        titel = args.get("titel", "")
        beschreibung = args.get("beschreibung", "")
        ideen_ids_str = args.get("ideen_ids", "")

        if not titel:
            return "Fehler: Kein Projekttitel angegeben."

        ideen_ids = [id.strip() for id in ideen_ids_str.split(",") if id.strip()] if ideen_ids_str else []

        project = Project(
            title=titel,
            description=beschreibung,
            ideas=ideen_ids,
        )
        await self._project_planner.create(project)

        return (
            f"Projekt erstellt! ID: {project.id}, Titel: '{titel}'. "
            f"{len(ideen_ids)} Ideen verknuepft."
        )

    async def _projekte_zeigen(self) -> str:
        projects = await self._project_planner.get_all()

        if not projects:
            return "Noch keine Projekte vorhanden."

        lines = [f"=== {len(projects)} Projekte ===\n"]
        for project in projects:
            lines.append(
                f"[{project.id}] {project.title} - {project.status} "
                f"({len(project.ideas)} Ideen)"
            )
            if project.description:
                lines.append(f"     {project.description[:100]}")

        return "\n".join(lines)


def create_agent() -> BaseAgent:
    """Factory-Funktion fuer Agent-Discovery."""
    return IdeasAgent()
