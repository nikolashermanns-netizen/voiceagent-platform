"""
Order Manager fuer Bestell-Agent.

Verwaltet Bestellungen waehrend eines Anrufs.
"""

import logging
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class OrderItem:
    """Einzelne Position in einer Bestellung."""

    def __init__(self, kennung: str, menge: int, produktname: str):
        self.kennung = kennung
        self.menge = menge
        self.produktname = produktname
        self.timestamp = datetime.now()

    def to_dict(self) -> dict:
        return {
            "kennung": self.kennung,
            "menge": self.menge,
            "produktname": self.produktname,
            "timestamp": self.timestamp.isoformat()
        }


class OrderManager:
    """
    Verwaltet die aktuelle Bestellung.
    Pro Anruf eine Bestellung, bei Anrufende geloescht.
    """

    def __init__(self):
        self._items: list[OrderItem] = []
        self._caller_id: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self.on_order_update: Optional[Callable[[dict], None]] = None

    def start_order(self, caller_id: str = None):
        """Startet eine neue Bestellung."""
        self._items = []
        self._caller_id = caller_id
        self._started_at = datetime.now()
        logger.info(f"Neue Bestellung gestartet fuer: {caller_id}")
        self._notify_update()

    def add_item(self, kennung: str, menge: int, produktname: str) -> bool:
        """Fuegt ein Produkt zur Bestellung hinzu."""
        # Pruefen ob Produkt bereits vorhanden
        for item in self._items:
            if item.kennung == kennung:
                item.menge += menge
                logger.info(
                    f"Bestellung aktualisiert: {menge}x {produktname} "
                    f"({kennung}) - jetzt {item.menge}x"
                )
                self._notify_update()
                return True

        item = OrderItem(kennung=kennung, menge=menge, produktname=produktname)
        self._items.append(item)
        logger.info(f"Bestellung hinzugefuegt: {menge}x {produktname} ({kennung})")
        self._notify_update()
        return True

    def remove_item(self, kennung: str) -> bool:
        """Entfernt ein Produkt aus der Bestellung."""
        for i, item in enumerate(self._items):
            if item.kennung == kennung:
                removed = self._items.pop(i)
                logger.info(f"Bestellung entfernt: {removed.produktname}")
                self._notify_update()
                return True
        return False

    def get_current_order(self) -> dict:
        """Gibt die aktuelle Bestellung zurueck."""
        return {
            "caller_id": self._caller_id,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "items": [item.to_dict() for item in self._items],
            "item_count": len(self._items),
            "total_quantity": sum(item.menge for item in self._items)
        }

    def get_order_summary(self) -> str:
        """Zusammenfassung fuer AI zum Vorlesen."""
        if not self._items:
            return "Die Bestellung ist leer."

        lines = ["Aktuelle Bestellung:"]
        for item in self._items:
            lines.append(f"- {item.menge}x {item.produktname}")

        lines.append(
            f"\nGesamt: {len(self._items)} Positionen, "
            f"{sum(item.menge for item in self._items)} Stueck"
        )
        return "\n".join(lines)

    def clear_order(self):
        """Loescht die aktuelle Bestellung."""
        count = len(self._items)
        self._items = []
        self._caller_id = None
        self._started_at = None
        logger.info(f"Bestellung geloescht ({count} Positionen)")
        self._notify_update()

    def _notify_update(self):
        """Benachrichtigt ueber Aenderungen."""
        if self.on_order_update:
            try:
                self.on_order_update(self.get_current_order())
            except Exception as e:
                logger.debug(f"Order update notification error: {e}")
