"""
BlacklistStore - Verwaltet gesperrte Rufnummern.

Speichert Blacklist-Eintraege und fehlgeschlagene Unlock-Versuche.
Auto-Blacklist: 3 fehlgeschlagene Anrufe in 12h -> automatisch gesperrt.
"""

import logging
from datetime import datetime, timedelta

from core.app.db.database import Database

logger = logging.getLogger(__name__)

# Auto-Blacklist Schwellenwerte
MAX_FAILED_CALLS = 3
FAILED_CALLS_WINDOW_HOURS = 12


class BlacklistStore:
    """Verwaltet die Rufnummern-Blacklist und fehlgeschlagene Anrufe."""

    def __init__(self, db: Database):
        self.db = db

    async def is_blacklisted(self, caller_id: str) -> bool:
        """Prueft ob eine Rufnummer gesperrt ist."""
        row = await self.db.fetch_one(
            "SELECT caller_id FROM blacklist WHERE caller_id = ?",
            (caller_id,)
        )
        return row is not None

    async def add(self, caller_id: str, reason: str = "") -> None:
        """Fuegt eine Rufnummer zur Blacklist hinzu."""
        await self.db.execute(
            "INSERT OR REPLACE INTO blacklist (caller_id, reason, blocked_at) VALUES (?, ?, ?)",
            (caller_id, reason, datetime.utcnow().isoformat())
        )
        logger.warning(f"[Blacklist] Nummer gesperrt: {caller_id} ({reason})")

    async def remove(self, caller_id: str) -> bool:
        """Entfernt eine Rufnummer von der Blacklist und loescht Failed-Call-Records."""
        row = await self.db.fetch_one(
            "SELECT caller_id FROM blacklist WHERE caller_id = ?",
            (caller_id,)
        )
        if not row:
            return False
        await self.db.execute(
            "DELETE FROM blacklist WHERE caller_id = ?",
            (caller_id,)
        )
        # Failed-Call-Records loeschen, damit 3 neue Fehlversuche noetig sind
        await self.db.execute(
            "DELETE FROM failed_unlock_calls WHERE caller_id = ?",
            (caller_id,)
        )
        logger.info(f"[Blacklist] Nummer entsperrt + Failed-Calls geloescht: {caller_id}")
        return True

    async def get_all(self) -> list[dict]:
        """Gibt alle Blacklist-Eintraege zurueck."""
        return await self.db.fetch_all(
            "SELECT caller_id, reason, blocked_at FROM blacklist ORDER BY blocked_at DESC"
        )

    async def record_failed_call(self, caller_id: str) -> None:
        """Zeichnet einen fehlgeschlagenen Anruf auf."""
        await self.db.execute(
            "INSERT INTO failed_unlock_calls (caller_id, failed_at) VALUES (?, ?)",
            (caller_id, datetime.utcnow().isoformat())
        )
        logger.info(f"[Blacklist] Fehlgeschlagener Anruf aufgezeichnet: {caller_id}")

    async def check_and_auto_blacklist(self, caller_id: str) -> bool:
        """
        Prueft ob eine Nummer automatisch gesperrt werden soll.
        Kriterium: >= 3 fehlgeschlagene Anrufe in den letzten 12 Stunden.

        Returns:
            True wenn die Nummer jetzt gesperrt wurde
        """
        if await self.is_blacklisted(caller_id):
            return False

        cutoff = (datetime.utcnow() - timedelta(hours=FAILED_CALLS_WINDOW_HOURS)).isoformat()
        row = await self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM failed_unlock_calls WHERE caller_id = ? AND failed_at > ?",
            (caller_id, cutoff)
        )

        count = row["cnt"] if row else 0
        if count >= MAX_FAILED_CALLS:
            await self.add(
                caller_id,
                f"Auto-Blacklist: {count} fehlgeschlagene Anrufe in {FAILED_CALLS_WINDOW_HOURS}h"
            )
            return True

        return False

    # ============== Whitelist ==============

    async def is_whitelisted(self, caller_id: str) -> bool:
        """Prueft ob eine Rufnummer auf der Whitelist steht."""
        row = await self.db.fetch_one(
            "SELECT caller_id FROM whitelist WHERE caller_id = ?",
            (caller_id,)
        )
        return row is not None

    async def add_to_whitelist(self, caller_id: str, note: str = "") -> None:
        """Fuegt eine Rufnummer zur Whitelist hinzu."""
        await self.db.execute(
            "INSERT OR REPLACE INTO whitelist (caller_id, note, added_at) VALUES (?, ?, ?)",
            (caller_id, note, datetime.utcnow().isoformat())
        )
        logger.info(f"[Whitelist] Nummer hinzugefuegt: {caller_id}")

    async def remove_from_whitelist(self, caller_id: str) -> bool:
        """Entfernt eine Rufnummer von der Whitelist. Returns True wenn gefunden."""
        row = await self.db.fetch_one(
            "SELECT caller_id FROM whitelist WHERE caller_id = ?",
            (caller_id,)
        )
        if not row:
            return False
        await self.db.execute(
            "DELETE FROM whitelist WHERE caller_id = ?",
            (caller_id,)
        )
        logger.info(f"[Whitelist] Nummer entfernt: {caller_id}")
        return True

    async def get_all_whitelist(self) -> list[dict]:
        """Gibt alle Whitelist-Eintraege zurueck."""
        return await self.db.fetch_all(
            "SELECT caller_id, note, added_at FROM whitelist ORDER BY added_at DESC"
        )
