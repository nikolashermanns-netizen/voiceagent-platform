# Agent-Navigation: Hauptagent als Zentrale mit Unteragenten

## Uebersicht

Der Anrufer startet immer beim **Hauptagent (Zentrale)**. Dieser begruesst, erklaert die
Moeglichkeiten und leitet per Sprachbefehl zum gewuenschten Fachagenten weiter.
Mit dem Wort **"exit"** kommt der Anrufer jederzeit zurueck zur Zentrale.

```
                    ┌─────────────────────┐
                    │    HAUPTAGENT        │
                    │    (Zentrale)        │
          ┌─────── │                     │ ───────┐
          │         │  "Was kann ich      │         │
          │         │   fuer dich tun?"   │         │
          │         └──────────┬──────────┘         │
          │                    │                    │
       "Coding"            "Ideen"          (weitere...)
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  CODE-AGENT     │ │  IDEEN-AGENT    │ │  Dynamisch      │
│  Programmieren  │ │  Ideen sammeln  │ │  erweiterbar    │
│  mit Claude CLI │ │  Projekte planen│ │                 │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                    │
         └───── "exit" ──────┴────── "exit" ──────┘
                             │
                    zurueck zur Zentrale
```

---

## Status: IMPLEMENTIERT

| Komponente | Status | Datei |
|------------|--------|-------|
| BaseAgent ABC | Fertig | `core/app/agents/base.py` |
| AgentRegistry (Auto-Discovery) | Fertig | `core/app/agents/registry.py` |
| AgentManager (Wechsel-Logik) | Fertig | `core/app/agents/manager.py` |
| VoiceClient.update_session() | Fertig | `core/app/ai/voice_client.py` |
| AgentRouter (Intent-Erkennung) | Fertig | `core/app/ai/agent_router.py` |
| **MainAgent (Zentrale)** | Fertig | `agents/main_agent/agent.py` |
| CodeAgent | Fertig | `agents/code_agent/agent.py` |
| IdeasAgent | Fertig | `agents/ideas_agent/agent.py` |
| Switch-Signal in on_function_call | Fertig | `core/app/main.py` |
| zurueck_zur_zentrale in allen Agents | Fertig | Alle agent.py Dateien |

---

## Architektur

### MainAgent (Zentrale)

- **Default-Agent** bei jedem Anruf
- Dynamische Agent-Liste aus der Registry (nicht hardcoded)
- Tools: `wechsel_zu_agent`, `zeige_optionen`
- Leitet nach Intent-Erkennung sofort weiter

### Agent-Switch Mechanismus

```
1. User sagt z.B. "Coding" oder "Ich moechte programmieren"
2. OpenAI erkennt Intent -> ruft wechsel_zu_agent(agent_name="code_agent") auf
3. MainAgent.execute_tool() gibt "__SWITCH__:code_agent" zurueck
4. on_function_call() in main.py erkennt das Signal
5. agent_manager.switch_agent("code_agent") wird aufgerufen
6. voice_client.update_session(tools, instructions) aktualisiert die OpenAI-Session
7. OpenAI antwortet mit neuem Agent-Persona und Begruessung
```

### Exit-Mechanismus

Jeder Fachagent hat das Tool `zurueck_zur_zentrale`:
- Reagiert auf "exit", "zurueck", "menue", "hauptmenue"
- Gibt `__SWITCH__:main_agent` zurueck
- Gleicher Mechanismus wie beim Hinwechseln

### Warum `__SWITCH__` Signal?

1. **Saubere Trennung**: Agents wissen nichts ueber die Plattform-Infrastruktur
2. **Einfachheit**: BaseAgent-Interface bleibt unveraendert
3. **Kontrolle**: main.py entscheidet ob der Switch erlaubt ist
4. **Testbarkeit**: Agents koennen isoliert getestet werden

---

## Gespraechsablauf (Beispiel)

```
[Anruf kommt rein -> main_agent startet]

KI:     "Hallo! Willkommen bei der VoiceAgent Zentrale. Was kann ich fuer dich tun?"

Anrufer: "Was kannst du alles?"

KI:     "Ich kann dich mit zwei Spezialisten verbinden:
         Den Programmier-Assistenten fuer Coding-Aufgaben,
         und den Ideen-Assistenten zum Ideen festhalten. Wohin soll es gehen?"

Anrufer: "Coding"

KI:     "Alles klar, ich verbinde dich mit dem Programmier-Assistenten."
        [-> wechsel_zu_agent("code_agent")]
        [-> Session-Update: neue Tools + Instructions]

KI:     "Hallo! Ich bin dein Programmier-Assistent. Was soll ich coden?"

Anrufer: "Erstelle mir eine FastAPI App mit User-Registration"
        [... normaler Coding-Vorgang ...]

Anrufer: "Exit"

KI:     "Alles klar, ich bringe dich zurueck zur Zentrale."
        [-> zurueck_zur_zentrale()]
        [-> Session-Update zurueck zum MainAgent]

KI:     "Willkommen zurueck! Was kann ich noch fuer dich tun?"

Anrufer: "Ideen"

KI:     "Alles klar, ich verbinde dich mit dem Ideen-Assistenten."
        [-> wechsel_zu_agent("ideas_agent")]

KI:     "Hallo! Ich bin dein Ideen-Assistent. Erzaehl mir von deiner Idee!"
```

---

## Session-Update bei Agent-Wechsel

Beim Switch passiert folgendes mit der OpenAI Realtime Session:
1. Tools werden komplett ausgetauscht (alte raus, neue rein)
2. Instructions (System-Prompt) wird komplett ausgetauscht
3. Die Konversationshistorie bleibt erhalten
4. Kein Disconnect/Reconnect noetig

## Erweiterbarkeit

Neue Agenten werden automatisch erkannt:
1. Neuen Ordner unter `agents/neuer_agent/` erstellen
2. `agent.py` mit `create_agent()` Factory implementieren
3. `zurueck_zur_zentrale` Tool + Instructions einbauen
4. Fertig - MainAgent zeigt den neuen Agent automatisch an
