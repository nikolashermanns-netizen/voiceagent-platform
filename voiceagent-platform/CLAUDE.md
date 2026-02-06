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
- Web-Dashboard hat einen "Blacklist" Tab mit Entfernen-Button (X)

## Konventionen
- Code-Kommentare und Docstrings auf Deutsch
- AI-Instructions (System-Prompts) auf Deutsch
- Tool-Namen auf Deutsch (lowercase mit underscores)
- Log-Messages koennen Deutsch und Englisch mischen
- Jedes Agent-Verzeichnis hat: `__init__.py`, `agent.py`, optionale Hilfsmodule
- GUI ist PySide6/Qt (NICHT web-basiert)
- Audio-Pipeline: 48kHz (PJSIP/Opus) <-> 16kHz/24kHz (OpenAI) via scipy Resampling
