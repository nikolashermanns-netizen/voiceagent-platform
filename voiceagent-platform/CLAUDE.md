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

## Konventionen
- Code-Kommentare und Docstrings auf Deutsch
- AI-Instructions (System-Prompts) auf Deutsch
- Tool-Namen auf Deutsch (lowercase mit underscores)
- Log-Messages koennen Deutsch und Englisch mischen
- Jedes Agent-Verzeichnis hat: `__init__.py`, `agent.py`, optionale Hilfsmodule
- GUI ist PySide6/Qt (NICHT web-basiert)
- Audio-Pipeline: 48kHz (PJSIP/Opus) <-> 16kHz/24kHz (OpenAI) via scipy Resampling
