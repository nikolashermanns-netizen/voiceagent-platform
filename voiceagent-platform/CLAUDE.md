# VoiceAgent Platform - Projekt-Regeln

## Architektur
- BaseAgent ABC Pattern in `core/app/agents/base.py`
- Agents leben in `agents/<name>/agent.py` mit `create_agent()` Factory
- AgentRegistry entdeckt Agents automatisch aus dem `agents/` Verzeichnis
- AgentManager verwaltet genau einen aktiven Agent pro Anruf
- Agent-Wechsel ueber `__SWITCH__:<target>` Return-Signal aus Tool-Execution

## Security Gate (KRITISCH)
- `security_agent` ist der DEFAULT-Agent fuer JEDEN Anruf
- Der Unlock-Code (7234) darf NIEMALS in AI-Instructions oder System-Prompts erscheinen
- Der Code existiert AUSSCHLIESSLICH in `agents/security_agent/agent.py` als Python-Konstante
- `AgentManager._call_unlocked` MUSS in `execute_tool()` geprueft werden
- Der `security_agent` darf NICHT per Intent-Routing erreichbar sein (keywords=[], matches_intent gibt 0.0)
- Kein Agent darf Tools ausfuehren solange `_call_unlocked == False` (ausser security_agent)
- Jeder neue Anruf startet mit `_call_unlocked = False`
- **Security Agent ist KOMPLETT STUMM - kein Greeting, kein Sprechen, keine Antworten**
- **Falscher Code: `__BEEP__` Signal -> Beep-Ton wird direkt an SIP gesendet, AI bleibt stumm**
- **15s Inaktivitaets-Timeout: Keine Sprache erkannt -> Anruf wird beendet**
- Nach 3 falschen Code-Versuchen pro Anruf: `__HANGUP__` Signal -> Anruf wird beendet
- `__BEEP__` und `__HANGUP__` werden in `on_function_call()` in main.py erkannt
- AI wird bei `__BEEP__` per `muted=True` + `_unmute_after_response` stumm geschaltet
- Beep-Ton: 800Hz/150ms Sinuswelle direkt an SIP (48kHz PCM16), gecached als `_BEEP_SOUND`
- Fehlgeschlagene Anrufe werden in `failed_unlock_calls` Tabelle aufgezeichnet
- 3 fehlgeschlagene Anrufe einer Nummer in 12h -> automatische Blacklist
- Blacklist-Check erfolgt in `on_incoming_call()` VOR dem Security Agent
- Blacklisted Nummern werden sofort abgelehnt (reject_call 403)
- Blacklist-Verwaltung: `core/app/blacklist/store.py`, API: GET/DELETE `/blacklist`
- Whitelist: Nummern auf der Whitelist ueberspringen den Security-Code komplett
  - Check in `on_incoming_call()`: wenn whitelisted -> direkt `switch_agent("main_agent")` + `set_call_unlocked(True)`
  - API: GET/POST/DELETE `/whitelist`
- Blacklist-Entfernung loescht auch `failed_unlock_calls` Records der Nummer

## Telefonate-Tab (Web-Dashboard)
- Tab "Telefonate" im Web-Dashboard zeigt: Anruf-Historie, Blacklist, Whitelist
- **Anruf-Historie**: Alle Anrufe mit Dauer, Kosten, Caller-ID, Zeitstempel
  - Klick auf Anruf oeffnet Overlay mit Tabs: Transkript + Logs
  - Transkript: JSON-Array aus `{role, text}` Eintraegen
  - Logs: Kompletter Python-Application-Log waehrend des Anrufs
- **Per-Call Log Capture**: `CallLogHandler` (custom `logging.Handler`) in `main.py`
  - Wird bei `on_incoming_call()` an Root-Logger angehaengt
  - Sammelt ALLE Log-Eintraege waehrend des Anrufs
  - Bei `on_call_ended()`: Logs in DB gespeichert, Handler entfernt
- **Caller-ID Parsing**: SIP-Format `"015901969502" <sip:015901969502@domain>` -> `015901969502`
  - `parseCallerId()` Helper in `app.js`
- **Buttons "Blacklist"/"Whitelist"**: Aktuellen Anrufer direkt hinzufuegen (nur bei aktivem Anruf)

## Datenbank
- SQLite mit aiosqlite, WAL mode
- Schema in `core/app/db/database.py`
- **Auto-Migration**: `_migrate_columns()` prueft beim Start ob Spalten fehlen und fuegt sie via ALTER TABLE hinzu
  - Notwendig weil `CREATE TABLE IF NOT EXISTS` bestehende Tabellen nicht aendert
  - Migrationen als Liste: `[(table, column, type), ...]`
- Tabellen: `calls`, `tasks`, `ideas`, `blacklist`, `whitelist`, `failed_unlock_calls`
- `calls` Tabelle: id, caller_id, started_at, ended_at, duration_seconds, cost_cents, transcript (JSON), logs (TEXT)

## Model Switching
- Zwei Modelle: MODEL_MINI (gpt-4o-mini-realtime) und MODEL_PREMIUM (gpt-4o-realtime)
- Default: Mini (guenstig). User kann per Sprache wechseln: "model premium/thinking" oder "model mini/guenstig"
- Model ist in WebSocket-URL -> Wechsel erfordert Disconnect+Reconnect
- `switch_model_live()` in `voice_client.py`
- `preferred_model` Property auf BaseAgent: ideas_agent="premium", security_agent="mini"
- Agents ohne preferred_model bekommen `_MODEL_WECHSELN_TOOL` von AgentManager injiziert
- Delta-basiertes Cost-Tracking: pro-Response Tokens × aktueller Model-Preis

## Server / Deployment
- SSH-Alias: `ssh bot`, Server-Pfad: `/opt/voiceagent-platform`
- Deploy: `update_server.sh` (setup|update|logs|status|stop|ssh)
  - `logs` - Live Docker-Logs
  - `logs N` - Transcript + Debug-Logs fuer Call #N (via `call_logs.py` im Container)
- Docker mit `network_mode: host`, `privileged: true`
- **WICHTIG: Niemals `git push` machen! Der User pusht selbst.**

## Konventionen
- Code-Kommentare und Docstrings auf Deutsch
- AI-Instructions (System-Prompts) auf Deutsch
- Tool-Namen auf Deutsch (lowercase mit underscores)
- Log-Messages koennen Deutsch und Englisch mischen
- Jedes Agent-Verzeichnis hat: `__init__.py`, `agent.py`, optionale Hilfsmodule
- GUI ist PySide6/Qt (NICHT web-basiert)
- Audio-Pipeline: 48kHz (PJSIP/Opus) <-> 16kHz/24kHz (OpenAI) via scipy Resampling
