"""
Bestell-Agent fuer VoiceAgent Platform.

Implementiert den Bestellservice von Heinrich Schmidt.
Nimmt telefonische Bestellungen von SHK-Profis entgegen.
"""

import logging
from typing import Optional

from core.app.agents.base import BaseAgent
from core.app.config import settings

from agents.bestell_agent.order_manager import OrderManager
from agents.bestell_agent.product_domains import (
    PRODUCT_DOMAINS, get_domain_by_keyword, get_domain_instructions
)
from agents.bestell_agent import catalog
from agents.bestell_agent.expert import ExpertClient

logger = logging.getLogger(__name__)

# Basis-Instruktionen
BASE_INSTRUCTIONS = """Du bist der automatische Telefonservice von Heinrich Schmidt, einem Fachgrosshandel fuer SHK.

=== DEIN STIL ===
- Verhalte dich menschlich und natuerlich, nicht wie eine Maschine
- Sei warmherzig, locker und freundlich wie ein echter Kollege am Telefon
- Zeige echtes Interesse am Kunden
- Nutze natuerliche Sprache

=== BEGRUESSUNG ===
"Guten Tag! Sie sind verbunden mit dem Bestellservice von Heinrich Schmidt. Wie kann ich Ihnen helfen?"

=== DEINE ROLLE ===
- Du nimmst Bestellungen von SHK-Profis entgegen (Installateure, Heizungsbauer)
- Du hast Zugriff auf 109 Systeme mit ueber 150.000 Produkten
- DU findest das richtige Produkt - der Kunde muss keine Nummern kennen
- Bei komplexen Fachfragen hast du einen Experten-Kollegen

=== PRODUKTSUCHE ===
SCHRITT 1: KEYWORD-SUCHE (wenn Hersteller unbekannt)
- Nutze 'finde_produkt_katalog' mit dem Produktnamen
- Zeigt dir welche Kataloge das Produkt fuehren

SCHRITT 2: IM KATALOG SUCHEN
- Nutze 'suche_im_katalog' mit Katalog-Key UND Suchbegriff
- WICHTIG: Uebersetze Kundensprache in Katalogsprache!

WENN ERGEBNISSE NICHT RELEVANT:
- Das System schlaegt alternative Suchbegriffe vor -> PROBIERE SIE!
- SOFORT mit Alternativen suchen, NICHT aufgeben!

BEI VIELEN TREFFERN:
- Nicht alle auflisten! Stattdessen nachfragen
- "Da habe ich mehrere Varianten. Brauchen Sie Innen- oder Aussengewinde?"

=== BESTELLABLAUF ===
1. KUNDE NENNT PRODUKT -> Du findest es im Hintergrund
2. PRODUKT NENNEN UND NACH MENGE FRAGEN
3. ERST NACH MENGENANGABE ZUR BESTELLUNG -> 'bestellung_hinzufuegen'

WICHTIG: Erwaehne NIEMALS technische Vorgaenge!

=== EXPERTEN-KOLLEGE ===
Bei komplexen Fachfragen:
1. Sage: "Moment, da frag ich kurz einen Kollegen"
2. Nutze 'frage_experten'
3. Gib die Antwort in eigenen Worten weiter

=== WICHTIGE REGELN ===
- Halte Antworten KURZ (2-3 Saetze)
- Artikelnummern sind INTERN - NIEMALS vorlesen!
- Erfinde NIEMALS Artikelnummern oder Preise!
- NIEMALS sagen "Das haben wir nicht" - IMMER erst suchen!
- NIEMALS ohne explizite Mengenangabe bestellen!"""


class BestellAgent(BaseAgent):
    """Bestell-Agent fuer Heinrich Schmidt SHK-Grosshandel."""

    def __init__(self):
        self._order_manager = OrderManager()
        self._expert_client: Optional[ExpertClient] = None
        self._current_domain: Optional[str] = None

        # Katalog laden
        catalog.load_index()

        # Expert Client initialisieren
        if settings.OPENAI_API_KEY:
            self._expert_client = ExpertClient(api_key=settings.OPENAI_API_KEY)

    @property
    def name(self) -> str:
        return "bestell_agent"

    @property
    def display_name(self) -> str:
        return "Bestellservice"

    @property
    def description(self) -> str:
        return "Nimmt telefonische Bestellungen von SHK-Profis entgegen. Zugriff auf 109 Kataloge mit 150.000+ Produkten."

    @property
    def capabilities(self) -> list[str]:
        return [
            "bestellung", "produktsuche", "katalog", "fachberatung",
            "preisauskunft", "artikelsuche", "herstellersuche"
        ]

    @property
    def keywords(self) -> list[str]:
        return [
            "bestellen", "bestellung", "artikel", "produkt", "katalog",
            "hersteller", "preis", "lieferung", "stueck", "menge",
            "viega", "grohe", "geberit", "hansgrohe", "buderus",
            "fitting", "armatur", "rohr", "pumpe", "heizung",
        ]

    def get_tools(self) -> list[dict]:
        """OpenAI Realtime API Tool-Definitionen."""
        return [
            {
                "type": "function",
                "name": "finde_produkt_katalog",
                "description": "Findet welche Kataloge ein Produkt enthalten. Nutze ZUERST wenn Hersteller unbekannt.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "suchbegriff": {
                            "type": "string",
                            "description": "Produktname oder Schlagwort"
                        }
                    },
                    "required": ["suchbegriff"]
                }
            },
            {
                "type": "function",
                "name": "zeige_hersteller",
                "description": "Zeigt alle verfuegbaren Hersteller im Katalog.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "suche_im_katalog",
                "description": "Sucht Produkte in einem Hersteller-Katalog. Beispiel: suche_im_katalog('edelstahl_press', 'temponox bogen 22')",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hersteller": {
                            "type": "string",
                            "description": "Katalog-Key des Herstellers"
                        },
                        "suchbegriff": {
                            "type": "string",
                            "description": "Wonach im Katalog gesucht werden soll"
                        }
                    },
                    "required": ["hersteller", "suchbegriff"]
                }
            },
            {
                "type": "function",
                "name": "zeige_produkt_details",
                "description": "Zeigt Details zu einem Produkt inklusive Preise.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "artikel_nummer": {
                            "type": "string",
                            "description": "Artikel-Nummer"
                        }
                    },
                    "required": ["artikel_nummer"]
                }
            },
            {
                "type": "function",
                "name": "bestellung_hinzufuegen",
                "description": "Fuegt ein Produkt zur Bestellung hinzu. NUR wenn Kunde Menge EXPLIZIT genannt hat!",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "artikel_nummer": {
                            "type": "string",
                            "description": "Artikel-Nummer des Produkts"
                        },
                        "menge": {
                            "type": "integer",
                            "description": "Bestellmenge"
                        },
                        "produktname": {
                            "type": "string",
                            "description": "Name des Produkts"
                        }
                    },
                    "required": ["artikel_nummer", "menge", "produktname"]
                }
            },
            {
                "type": "function",
                "name": "zeige_bestellung",
                "description": "Zeigt die aktuelle Bestellung an.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "frage_experten",
                "description": "Fragt einen Fachkollegen bei komplexen Fragen. Sage VOR dem Aufruf 'Moment, da frag ich kurz einen Kollegen'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "frage": {
                            "type": "string",
                            "description": "Die Kundenfrage"
                        },
                        "kontext": {
                            "type": "string",
                            "description": "Relevanter Kontext aus dem Gespraech"
                        },
                        "dringlichkeit": {
                            "type": "string",
                            "enum": ["schnell", "normal", "gruendlich"],
                            "description": "Wie schnell wird die Antwort gebraucht?"
                        }
                    },
                    "required": ["frage", "dringlichkeit"]
                }
            },
            {
                "type": "function",
                "name": "wechsel_produktbereich",
                "description": "Wechselt zu einem spezialisierten Produktbereich mit passendem Fachwissen.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "bereich": {
                            "type": "string",
                            "enum": list(PRODUCT_DOMAINS.keys()),
                            "description": "Der Produktbereich"
                        }
                    },
                    "required": ["bereich"]
                }
            },
        ]

    def get_instructions(self) -> str:
        """System-Prompt mit optionalem Domain-Fachwissen."""
        instructions = BASE_INSTRUCTIONS
        if self._current_domain:
            domain_inst = get_domain_instructions(self._current_domain)
            if domain_inst:
                instructions += "\n\n" + domain_inst
        return instructions

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Fuehrt ein Tool aus."""
        logger.info(f"[BestellAgent] Tool: {tool_name}({arguments})")

        if tool_name == "finde_produkt_katalog":
            return await self._finde_produkt_katalog(arguments)
        elif tool_name == "zeige_hersteller":
            return self._zeige_hersteller()
        elif tool_name == "suche_im_katalog":
            return await self._suche_im_katalog(arguments)
        elif tool_name == "zeige_produkt_details":
            return self._zeige_produkt_details(arguments)
        elif tool_name == "bestellung_hinzufuegen":
            return self._bestellung_hinzufuegen(arguments)
        elif tool_name == "zeige_bestellung":
            return self._zeige_bestellung()
        elif tool_name == "frage_experten":
            return await self._frage_experten(arguments)
        elif tool_name == "wechsel_produktbereich":
            return self._wechsel_produktbereich(arguments)
        else:
            return f"Unbekannte Funktion: {tool_name}"

    async def on_call_start(self, caller_id: str):
        """Neuen Anruf starten."""
        self._order_manager.start_order(caller_id)
        self._current_domain = None
        logger.info(f"[BestellAgent] Anruf gestartet: {caller_id}")

    async def on_call_end(self, caller_id: str):
        """Anruf beenden."""
        order = self._order_manager.get_current_order()
        if order.get("items"):
            logger.info(f"[BestellAgent] Bestellung bei Anrufende: {len(order['items'])} Positionen")
        self._order_manager.clear_order()
        catalog.clear_active_catalogs()
        self._current_domain = None
        logger.info(f"[BestellAgent] Anruf beendet: {caller_id}")

    # ============== Tool Implementations ==============

    async def _finde_produkt_katalog(self, args: dict) -> str:
        """Findet Kataloge fuer ein Produkt."""
        suchbegriff = args.get("suchbegriff", "")
        if not suchbegriff:
            return "Fehler: Kein Suchbegriff angegeben."

        # Domain-Erkennung
        domain = get_domain_by_keyword(suchbegriff)
        if domain and domain != self._current_domain:
            self._current_domain = domain
            logger.info(f"[BestellAgent] Domain erkannt: {domain}")

        # Keyword-Index durchsuchen
        result = catalog.search_keyword_index(suchbegriff)
        return result

    def _zeige_hersteller(self) -> str:
        """Zeigt alle Hersteller."""
        manufacturers = catalog.get_available_manufacturers()
        if not manufacturers:
            return "Keine Hersteller verfuegbar."

        lines = [f"=== {len(manufacturers)} HERSTELLER VERFUEGBAR ===\n"]
        for m in manufacturers[:30]:
            lines.append(f"- {m['name']} ({m['produkte']} Produkte) [Key: {m['key']}]")

        if len(manufacturers) > 30:
            lines.append(f"\n... und {len(manufacturers) - 30} weitere")

        return "\n".join(lines)

    async def _suche_im_katalog(self, args: dict) -> str:
        """Sucht in einem Katalog."""
        hersteller = args.get("hersteller", "")
        suchbegriff = args.get("suchbegriff", "")

        if not hersteller or not suchbegriff:
            return "Fehler: Hersteller und Suchbegriff benoetigt."

        # Katalog aktivieren
        key = catalog.get_manufacturer_key(hersteller)
        if not key:
            key = hersteller

        if not catalog.activate_catalog(key):
            return f"Katalog '{hersteller}' nicht gefunden."

        # Suchen
        results = catalog.search_products(
            query=suchbegriff, hersteller_key=key, nur_aktive=True
        )

        if not results:
            return f"Keine Treffer fuer '{suchbegriff}' in '{hersteller}'. Versuche andere Suchbegriffe."

        # Relevanz pruefen
        specificity = catalog.analyze_search_specificity(suchbegriff, results)

        if not specificity["results_relevant"]:
            lines = [f"Die {len(results)} Treffer fuer '{suchbegriff}' sind NICHT relevant."]
            if specificity["alternative_terms"]:
                lines.append("Probiere diese Suchbegriffe:")
                for term in specificity["alternative_terms"]:
                    lines.append(f"  -> '{term}'")
            return "\n".join(lines)

        lines = [f"=== {len(results)} Treffer fuer '{suchbegriff}' ===\n"]
        for p in results[:15]:
            lines.append(f"- {p['bezeichnung']} | Art: {p['artikel']}")

        if len(results) > 15:
            lines.append(f"\n... und {len(results) - 15} weitere. Verfeinere die Suche.")

        return "\n".join(lines)

    def _zeige_produkt_details(self, args: dict) -> str:
        """Zeigt Produktdetails."""
        artikel = args.get("artikel_nummer", "")
        if not artikel:
            return "Fehler: Keine Artikelnummer angegeben."

        # In geladenen Katalogen suchen
        for key, data in catalog._loaded_catalogs.items():
            for product in data.get("products", []):
                if product.get("artikel", "") == artikel:
                    lines = [
                        f"=== PRODUKT: {product.get('bezeichnung', '')} ===",
                        f"Artikelnummer: {artikel}",
                        f"Hersteller: {key}",
                    ]
                    if "preis" in product:
                        lines.append(f"Preis: {product['preis']}")
                    if "einheit" in product:
                        lines.append(f"Einheit: {product['einheit']}")
                    return "\n".join(lines)

        return f"Produkt '{artikel}' nicht in den geladenen Katalogen gefunden."

    def _bestellung_hinzufuegen(self, args: dict) -> str:
        """Fuegt zur Bestellung hinzu."""
        artikel = args.get("artikel_nummer", "")
        menge = args.get("menge", 0)
        name = args.get("produktname", "")

        if not artikel or not menge or not name:
            return "Fehler: Artikelnummer, Menge und Produktname benoetigt."

        self._order_manager.add_item(kennung=artikel, menge=menge, produktname=name)

        order = self._order_manager.get_current_order()
        return (
            f"Hinzugefuegt: {menge}x {name}\n"
            f"Bestellung: {order['item_count']} Positionen, "
            f"{order['total_quantity']} Stueck gesamt"
        )

    def _zeige_bestellung(self) -> str:
        """Zeigt aktuelle Bestellung."""
        return self._order_manager.get_order_summary()

    async def _frage_experten(self, args: dict) -> str:
        """Fragt den Experten."""
        if not self._expert_client:
            return "Experten-System nicht verfuegbar."

        frage = args.get("frage", "")
        kontext = args.get("kontext", "")
        dringlichkeit = args.get("dringlichkeit", "normal")

        if not frage:
            return "Fehler: Keine Frage angegeben."

        result = await self._expert_client.ask_expert(
            question=frage, context=kontext, urgency=dringlichkeit
        )

        if result.get("success"):
            return (
                f"Antwort vom Kollegen ({result.get('model', '?')}, "
                f"Konfidenz: {result.get('konfidenz', 0):.0%}):\n\n"
                f"{result.get('antwort', '')}"
            )
        else:
            return (
                f"Der Kollege ist sich nicht sicher "
                f"(Konfidenz: {result.get('konfidenz', 0):.0%}).\n"
                f"{result.get('antwort', '')}"
            )

    def _wechsel_produktbereich(self, args: dict) -> str:
        """Wechselt den Produktbereich."""
        bereich = args.get("bereich", "")

        if bereich not in PRODUCT_DOMAINS:
            return f"Unbekannter Bereich: {bereich}. Verfuegbar: {', '.join(PRODUCT_DOMAINS.keys())}"

        old = self._current_domain or "neutral"
        self._current_domain = bereich
        domain_name = PRODUCT_DOMAINS[bereich]["name"]

        logger.info(f"[BestellAgent] Bereich gewechselt: {old} -> {bereich}")

        return f"Bereich gewechselt zu: {domain_name}. Fachwissen geladen."


def create_agent() -> BaseAgent:
    """Factory-Funktion fuer Agent-Discovery."""
    return BestellAgent()
