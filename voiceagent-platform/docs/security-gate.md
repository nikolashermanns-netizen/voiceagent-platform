# Security Gate Agent

## Uebersicht
Das Security Gate ist der erste Kontaktpunkt fuer jeden eingehenden Anruf.
Der Anrufer muss einen numerischen Entsperr-Code nennen, bevor er
Zugang zu den Fachagenten der Plattform bekommt.

## Architektur

### Defense-in-Depth (2 Sicherheits-Ebenen)

**Ebene 1 - Agent-System:**
Der `security_agent` ist der Default-Agent fuer jeden Anruf.
Nur das `unlock`-Tool wird an OpenAI gesendet. Die AI hat keine
Kenntnis des korrekten Codes - die Validierung passiert ausschliesslich
in Python serverseitig.

**Ebene 2 - Server-Flag:**
`AgentManager._call_unlocked` ist ein Boolean der fuer jeden Anruf
als `False` startet. Selbst wenn die OpenAI-Session manipuliert wuerde,
blockiert `AgentManager.execute_tool()` alle nicht-Security-Tools
solange das Flag `False` ist.

### Call-Flow

```
Eingehender Anruf
    |
    v
security_agent aktiviert (Default-Agent)
    |
    v
AI fragt Anrufer nach Entsperr-Code
    |
    v
Anrufer spricht Code -> AI ruft unlock(code="...") auf
    |
    v
SecurityAgent.execute_tool() prueft Code in Python
    |
    +-- Falscher Code --> Fehlermeldung, AI fragt erneut
    |
    +-- Richtiger Code --> return __SWITCH__:main_agent
        |
        v
    main.py on_function_call() erkennt __SWITCH__
        |
        v
    AgentManager.switch_agent("main_agent")
    + AgentManager.set_call_unlocked(True)
        |
        v
    VoiceClient.update_session() mit main_agent Tools/Instructions
        |
        v
    Normaler Betrieb (alle Agenten verfuegbar)
```

### Sicherheitseigenschaften

- Der Unlock-Code existiert NUR in `agents/security_agent/agent.py`
  als Python-Konstante `_UNLOCK_CODE`
- Die AI-Instructions sagen explizit: "Du KENNST den Code NICHT"
- Die AI erhaelt nie den Code - nur "korrekt" (via `__SWITCH__`) oder "falsch" (Fehlermeldung)
- Das Server-Flag `_call_unlocked` bietet Defense-in-Depth
- `security_agent` hat `keywords = []` und `matches_intent()` gibt 0.0 zurueck -
  kann nicht per Intent-Routing erreicht werden
- Per-Call State: `_call_unlocked` wird bei `start_call()` und `end_call()` zurueckgesetzt

### Code aendern

Den Entsperr-Code aendern: `_UNLOCK_CODE` in `agents/security_agent/agent.py` editieren.
Keine weiteren Dateien muessen angepasst werden.

### Beteiligte Dateien

| Datei | Rolle |
|-------|-------|
| `agents/security_agent/agent.py` | SecurityAgent mit unlock-Tool und Code-Validierung |
| `core/app/agents/manager.py` | `_call_unlocked` Flag und Security-Check in `execute_tool()` |
| `core/app/main.py` | Default-Agent = security_agent, setzt Unlock-Flag bei Switch |
| `agents/main_agent/agent.py` | Schliesst security_agent aus der Agent-Liste aus |
