"""
SQLite Datenbank-Layer mit aiosqlite.
"""

import asyncio
import json
import logging
import os
import sqlite3
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

# Schema Version fuer Migrationen
SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Tasks von allen Agenten
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending',
    result TEXT,
    error TEXT,
    progress REAL DEFAULT 0.0,
    caller_id TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ideen-Datenbank (fuer Ideas Agent)
CREATE TABLE IF NOT EXISTS ideas (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    priority INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    tags TEXT DEFAULT '[]',
    notes TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projekte (fuer Ideas Agent)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'planning',
    ideas TEXT DEFAULT '[]',
    tasks TEXT DEFAULT '[]',
    plan TEXT,
    milestones TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Anruf-History
CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY,
    caller_id TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    duration_seconds INTEGER,
    cost_cents REAL DEFAULT 0.0,
    agents_used TEXT DEFAULT '[]',
    tasks_created TEXT DEFAULT '[]',
    transcript TEXT DEFAULT '[]',
    logs TEXT DEFAULT '',
    summary TEXT
);

-- Agent-Konfigurationen
CREATE TABLE IF NOT EXISTS agent_configs (
    agent_name TEXT PRIMARY KEY,
    config TEXT DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Blacklist (gesperrte Rufnummern)
CREATE TABLE IF NOT EXISTS blacklist (
    caller_id TEXT PRIMARY KEY,
    reason TEXT,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fehlgeschlagene Unlock-Anrufe (fuer Auto-Blacklist)
CREATE TABLE IF NOT EXISTS failed_unlock_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_id TEXT NOT NULL,
    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Whitelist (Nummern die Security-Code ueberspringen)
CREATE TABLE IF NOT EXISTS whitelist (
    caller_id TEXT PRIMARY KEY,
    note TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schema-Version
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """Async SQLite Datenbank-Manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """Datenbank initialisieren und Schema erstellen."""
        # Verzeichnis erstellen falls nicht vorhanden
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # WAL-Modus fuer bessere Concurrent-Performance
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

        # Schema erstellen
        await self._db.executescript(SCHEMA_SQL)

        # Migrationen: fehlende Spalten hinzufuegen (ALTER TABLE IF NOT EXISTS gibt es nicht)
        await self._migrate_columns()

        # Schema-Version setzen
        await self._db.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,)
        )
        await self._db.commit()

        logger.info(f"Datenbank initialisiert: {self.db_path}")

    async def _migrate_columns(self):
        """Fuegt fehlende Spalten zu bestehenden Tabellen hinzu."""
        migrations = [
            ("calls", "cost_cents", "REAL DEFAULT 0.0"),
            ("calls", "logs", "TEXT DEFAULT ''"),
        ]
        for table, column, col_type in migrations:
            try:
                await self._db.execute(f"SELECT {column} FROM {table} LIMIT 0")
            except Exception:
                logger.info(f"Migration: {table}.{column} hinzufuegen")
                await self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                await self._db.commit()

    async def close(self):
        """Datenbank-Verbindung schliessen."""
        if self._db:
            await self._db.close()
            self._db = None

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """SQL ausfuehren."""
        cursor = await self._db.execute(sql, params)
        await self._db.commit()
        return cursor

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Eine Zeile abfragen."""
        cursor = await self._db.execute(sql, params)
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Alle Zeilen abfragen."""
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# Globale Datenbank-Instanz
_db: Optional[Database] = None


async def get_database() -> Database:
    """Gibt die globale Datenbank-Instanz zurueck."""
    global _db
    if _db is None:
        from core.app.config import settings
        _db = Database(settings.DATABASE_PATH)
        await _db.initialize()
    return _db


async def close_database():
    """Schliesst die globale Datenbank-Verbindung."""
    global _db
    if _db:
        await _db.close()
        _db = None
