# Integrationsplan: Claude CLI als Coding Agent

## Ziel

Den bestehenden `code_agent` durch eine Claude CLI-Integration ersetzen, sodass der
Voice-Agent echte Software-Engineering-Aufgaben ausfuehren kann: Code verstehen, schreiben,
debuggen, refactoren -- gesteuert per Sprache oder GUI.

---

## Status Quo

Der aktuelle `code_agent` hat 4 simple Tools:
- `code_schreiben` -- Datei schreiben
- `code_ausfuehren` -- Code in Docker-Sandbox ausfuehren
- `dateien_zeigen` -- Dateien auflisten
- `datei_lesen` -- Datei lesen

**Problem:** Kein Code-Verstaendnis, kein intelligentes Editing, kein Debugging, keine
Codebase-Navigation. Der Agent ist im Grunde ein glorifizierter File-Editor.

---

## Integrationsmethode: Python Agent SDK (`claude-agent-sdk`)

### Warum SDK statt CLI-Subprocess?

| Kriterium | CLI (`claude -p`) | Python Agent SDK |
|-----------|-------------------|------------------|
| Structured Output | JSON parsing noetig | Native Python-Objekte |
| Streaming | stdout parsing | Async Iterator |
| Session Management | Session-IDs manuell | Eingebaut |
| Error Handling | Exit-Codes | Python Exceptions |
| Tool-Kontrolle | CLI-Flags | Programmatisch |
| Passt zu FastAPI | Maessig | Perfekt (async) |

**Entscheidung:** `claude-agent-sdk` (Python) als primaere Integration.
CLI (`claude -p`) als Fallback fuer einfache One-Shot-Queries.

---

## Architektur

```
┌─────────────────────────────────────────────────────┐
│                   Voice / GUI                        │
│         "Bau mir eine REST API fuer User"           │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│              OpenAI Realtime API                      │
│         (Voice-zu-Text, Intent, Tool Calls)          │
└──────────────┬───────────────────────────────────────┘
               │ function_call: "coding_task"
               ▼
┌──────────────────────────────────────────────────────┐
│              CodeAgent (refactored)                    │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │           ClaudeCodingBridge                      │ │
│  │                                                   │ │
│  │  - claude-agent-sdk query()                      │ │
│  │  - Working Directory = Projekt-Workspace         │ │
│  │  - Erlaubte Tools: Read, Edit, Write, Bash,     │ │
│  │    Glob, Grep, Task                              │ │
│  │  - System Prompt mit Projekt-Kontext             │ │
│  │  - Streaming Progress via WebSocket              │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │           Session Manager                         │ │
│  │  - Session pro Projekt persistieren              │ │
│  │  - Kontext ueber mehrere Auftraege behalten      │ │
│  │  - Resume/Fork fuer Folge-Auftraege              │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
               │
               ▼ Progress-Updates
┌──────────────────────────────────────────────────────┐
│              WebSocket → GUI                          │
│  - Live-Streaming: Was Claude gerade tut             │
│  - Tool-Ausfuehrungen in Echtzeit                    │
│  - Ergebnis-Zusammenfassung per Voice                │
└──────────────────────────────────────────────────────┘
```

---

## Implementierung in 5 Phasen

### Phase 1: Foundation -- ClaudeCodingBridge

**Neue Datei:** `agents/code_agent/claude_bridge.py`

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

class ClaudeCodingBridge:
    """Wrapper um claude-agent-sdk fuer den CodeAgent."""

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.sessions: dict[str, str] = {}  # project_id -> session_id

    async def execute_task(
        self,
        prompt: str,
        project_id: str,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> CodingResult:
        """Fuehrt eine Coding-Aufgabe mit Claude aus."""

        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
            permission_mode="acceptEdits",
            cwd=os.path.join(self.workspace_dir, project_id),
            max_turns=30,
            system_prompt=self._build_system_prompt(project_id),
        )

        # Session fortsetzen wenn vorhanden
        if project_id in self.sessions:
            options.resume = self.sessions[project_id]

        result_text = ""
        files_changed = []

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and on_progress:
                        await on_progress(block.text)
                    elif hasattr(block, "name"):
                        # Tool-Ausfuehrung tracken
                        if on_progress:
                            await on_progress(f"[Tool: {block.name}]")

            elif isinstance(message, ResultMessage):
                result_text = message.result or ""
                if hasattr(message, "session_id"):
                    self.sessions[project_id] = message.session_id

        return CodingResult(
            summary=result_text,
            files_changed=files_changed,
            session_id=self.sessions.get(project_id),
        )
```

**Aufwand:** Neue Klasse, ~150 Zeilen

---

### Phase 2: CodeAgent Refactoring

**Datei:** `agents/code_agent/agent.py` -- bestehende Tools ersetzen

**Vorher (4 granulare Tools):**
```
code_schreiben, code_ausfuehren, dateien_zeigen, datei_lesen
```

**Nachher (2 high-level Tools):**

| Tool | Beschreibung | Wann |
|------|-------------|------|
| `coding_aufgabe` | Komplexe Coding-Aufgabe an Claude delegieren | Features, Bugs, Refactoring |
| `projekt_status` | Aktuellen Stand eines Projekts abfragen | "Was haben wir bisher gemacht?" |

```python
def get_tools(self) -> list[dict]:
    return [
        {
            "type": "function",
            "name": "coding_aufgabe",
            "description": (
                "Fuehrt eine Programmier-Aufgabe aus: Code schreiben, Bugs fixen, "
                "Dateien bearbeiten, Tests laufen lassen. Nutzt Claude CLI im Hintergrund."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "aufgabe": {
                        "type": "string",
                        "description": "Beschreibung der Aufgabe, z.B. 'Erstelle eine FastAPI Route fuer User-Registration'"
                    },
                    "projekt": {
                        "type": "string",
                        "description": "Projekt-Name oder ID"
                    }
                },
                "required": ["aufgabe"]
            }
        },
        {
            "type": "function",
            "name": "projekt_status",
            "description": "Zeigt den aktuellen Stand und die Dateien eines Projekts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "projekt": {"type": "string", "description": "Projekt-Name oder ID"}
                },
                "required": ["projekt"]
            }
        }
    ]
```

**Kernlogik in `execute_tool`:**
```python
async def execute_tool(self, tool_name: str, arguments: dict) -> str:
    if tool_name == "coding_aufgabe":
        project_id = arguments.get("projekt", "default")

        # Task im Hintergrund starten (lange Laufzeit)
        task = Task(
            agent_name=self.name,
            description=arguments["aufgabe"],
            metadata={"project_id": project_id}
        )
        await self.task_store.create(task)

        # Claude-Bridge async ausfuehren
        result = await self.bridge.execute_task(
            prompt=arguments["aufgabe"],
            project_id=project_id,
            on_progress=lambda msg: self._broadcast_progress(msg),
        )

        task.status = TaskStatus.COMPLETED
        task.result = result.summary
        await self.task_store.update(task)

        # Sprachfreundliche Zusammenfassung zurueckgeben
        return self._summarize_for_voice(result)
```

**Aufwand:** Refactoring bestehender agent.py, ~100 Zeilen Aenderungen

---

### Phase 3: Async Task Integration

Coding-Aufgaben koennen laenger dauern. Der Voice-Agent soll nicht blockieren.

**Ablauf:**
1. User: "Bau mir eine REST API fuer User-Management"
2. OpenAI Tool Call → `coding_aufgabe`
3. Agent erstellt Task, startet Claude-Bridge im Hintergrund
4. Agent antwortet sofort: "Ich arbeite daran. Du kannst weitersprechen."
5. Progress-Updates via WebSocket an GUI
6. Nach Abschluss: Voice-Benachrichtigung "Die REST API ist fertig. 5 Dateien erstellt."

**Neuer WebSocket Message-Type:**
```python
# Neuer Message-Type fuer die GUI
{
    "type": "coding_progress",
    "task_id": "abc123",
    "project_id": "my-api",
    "status": "running",           # running | completed | failed
    "current_action": "Erstelle models/user.py",
    "progress": 0.4,
    "details": "Schreibe User-Model mit SQLAlchemy..."
}
```

**GUI-Erweiterung (Phase 5):**
- Neues Panel: "Coding Tasks" mit Live-Fortschritt
- Diff-Viewer fuer geaenderte Dateien
- Terminal-Output von Bash-Ausfuehrungen

---

### Phase 4: Session & Kontext-Management

Claude-Sessions projektbezogen persistieren, damit Folge-Auftraege Kontext haben.

**Datei:** `agents/code_agent/session_store.py`

```python
class CodingSessionStore:
    """Persistiert Claude-Sessions pro Projekt in SQLite."""

    async def save_session(self, project_id: str, session_id: str, summary: str): ...
    async def get_session(self, project_id: str) -> str | None: ...
    async def list_sessions(self, project_id: str) -> list[SessionInfo]: ...
    async def clear_session(self, project_id: str): ...
```

**Nutzung:**
```
User: "Erstelle eine User-Klasse mit Name und Email"
→ Claude erstellt user.py, Session wird gespeichert

User: "Fuege noch ein Passwort-Feld hinzu"
→ Claude resumed die Session, kennt den bisherigen Code
→ Aendert user.py statt neu zu erstellen
```

---

### Phase 5: Sicherheit & Sandboxing

Claude CLI hat Zugriff auf Dateisystem und Bash. Das muss eingeschraenkt werden.

**Massnahmen:**

1. **Working Directory einschraenken:**
   - `cwd` auf `/app/workspace/{project_id}` setzen
   - Claude kann nur innerhalb des Projekt-Ordners arbeiten

2. **Tool-Einschraenkungen:**
   ```python
   allowed_tools = [
       "Read", "Edit", "Write", "Glob", "Grep",
       "Bash(python *)",        # Nur Python ausfuehren
       "Bash(npm *)",           # npm erlaubt
       "Bash(node *)",          # node erlaubt
       "Bash(pip install *)",   # Dependencies installieren
       "Bash(pytest *)",        # Tests laufen lassen
       "Bash(git *)",           # Git-Operationen
   ]
   ```

3. **Docker-Isolation (bestehend):**
   - Claude CLI laeuft innerhalb des Core-Containers
   - Netzwerk nur fuer Anthropic API noetig (nicht `--network none`)
   - Memory/CPU Limits via Docker Compose

4. **Max Budget:**
   ```python
   options = ClaudeAgentOptions(
       max_budget_usd=2.00,  # Pro Aufgabe
       max_turns=50,         # Maximale Iterationen
   )
   ```

---

## Abhaengigkeiten & Setup

### Neue Python-Dependency
```
# core/requirements.txt
claude-agent-sdk>=0.1.0
```

### Umgebungsvariablen
```env
# .env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-20250514    # Default-Modell fuer Coding
CLAUDE_MAX_BUDGET=2.00                    # Max USD pro Aufgabe
CLAUDE_MAX_TURNS=50                       # Max Iterationen
```

### Dockerfile-Aenderung
```dockerfile
# Node.js wird benoetigt fuer Claude CLI/SDK
RUN apt-get update && apt-get install -y nodejs npm
RUN npm install -g @anthropic-ai/claude-code
```

---

## Config-Erweiterung

**Datei:** `core/app/config.py`

```python
# Claude Coding Agent
ANTHROPIC_API_KEY: str = ""
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
CLAUDE_MAX_BUDGET: float = 2.0
CLAUDE_MAX_TURNS: int = 50
CLAUDE_ALLOWED_TOOLS: list[str] = [
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(python *)", "Bash(npm *)", "Bash(pytest *)", "Bash(git *)",
]
```

---

## Neue/Geaenderte Dateien

| Datei | Aktion | Beschreibung |
|-------|--------|-------------|
| `agents/code_agent/claude_bridge.py` | **NEU** | Claude SDK Wrapper |
| `agents/code_agent/session_store.py` | **NEU** | Session-Persistierung |
| `agents/code_agent/agent.py` | **AENDERN** | Tools ersetzen, Bridge integrieren |
| `agents/code_agent/sandbox.py` | **ENTFERNEN** | Wird durch Claude CLI ersetzt |
| `agents/code_agent/project_manager.py` | **VEREINFACHEN** | Nur noch Projekt-Metadaten |
| `core/app/config.py` | **ERWEITERN** | Claude-Settings |
| `core/app/api/ws_routes.py` | **ERWEITERN** | `coding_progress` Message-Type |
| `core/requirements.txt` | **ERWEITERN** | `claude-agent-sdk` |
| `core/Dockerfile` | **ERWEITERN** | Node.js + Claude CLI |
| `docker-compose.yml` | **ERWEITERN** | `ANTHROPIC_API_KEY` env |
| `gui/main_window.py` | **ERWEITERN** | Coding-Task-Panel (optional) |

---

## Beispiel-Flow: Ende-zu-Ende

```
1. User ruft an: "Hey, ich brauche eine FastAPI App mit User-Registration"

2. OpenAI erkennt Intent → code_agent aktiviert

3. OpenAI generiert Tool Call:
   coding_aufgabe(
     aufgabe="Erstelle eine FastAPI App mit User-Registration. "
             "Brauche Endpoints: POST /register, POST /login, GET /me. "
             "Nutze SQLite und Pydantic Models.",
     projekt="user-api"
   )

4. CodeAgent:
   a) Erstellt Projekt-Ordner: /app/workspace/user-api/
   b) Erstellt Task in DB (status: RUNNING)
   c) Startet ClaudeCodingBridge.execute_task()

5. Claude CLI (via SDK):
   - Erstellt main.py mit FastAPI Setup
   - Erstellt models/user.py mit Pydantic
   - Erstellt db.py mit SQLite
   - Erstellt routes/auth.py mit Endpoints
   - Erstellt requirements.txt
   - Fuehrt pytest aus → alles gruen

6. Progress-Updates via WebSocket:
   → "Erstelle Projektstruktur..."
   → "Schreibe User-Model..."
   → "Implementiere Auth-Endpoints..."
   → "Laufe Tests..."
   → "Fertig! 5 Dateien erstellt, alle Tests bestanden."

7. Voice-Antwort: "Die FastAPI App ist fertig. Ich habe 5 Dateien
   erstellt mit Registration, Login und einem Me-Endpoint. Alle
   Tests laufen durch. Soll ich noch etwas aendern?"

8. User: "Fuege noch Email-Validierung hinzu"
   → Claude resumed Session, kennt den Code
   → Aendert nur die relevanten Stellen
```

---

## Offene Fragen

1. **Modell-Wahl:** Sonnet (schnell, guenstig) vs Opus (beste Qualitaet) -- konfigurierbar machen?
2. **Concurrent Tasks:** Mehrere Coding-Aufgaben parallel? Oder Queue?
3. **GUI Diff-Viewer:** Eigenes Widget oder externe Loesung (Monaco Editor)?
4. **Git-Integration:** Automatisch committen nach jeder Aufgabe?
5. **Code-Review:** Zweiter Claude-Pass als Review vor Abschluss?
