"""
VoiceAgent Platform - FastAPI Main Entry Point.

Verbindet alle Komponenten: SIP, AI, Agents, Tasks, WebSocket.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.app.config import settings
from core.app.db.database import get_database
from core.app.sip.sip_client import SIPClient
from core.app.sip.audio import sip_to_ai_input, ai_output_to_sip
from core.app.ai.voice_client import VoiceClient
from core.app.ai.agent_router import AgentRouter
from core.app.agents.registry import AgentRegistry
from core.app.agents.manager import AgentManager
from core.app.tasks.store import TaskStore
from core.app.tasks.executor import TaskExecutor
from core.app.ws.manager import ConnectionManager
from core.app.blacklist.store import BlacklistStore
from core.app.api.routes import setup_routes, is_ip_allowed
from core.app.api.ws_routes import setup_ws_routes

# Logging Setup
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============== App State ==============
# Alle Komponenten werden hier gehalten und an Routes weitergegeben

app_state = {}


# ============== Audio Stats ==============

_audio_stats = {
    "caller_to_ai": 0,
    "ai_to_caller": 0,
    "caller_bytes": 0,
    "ai_bytes": 0,
}


# ============== Event Handlers ==============

async def on_incoming_call(caller_id: str, remote_ip: str = None):
    """Eingehender Anruf."""
    sip_client: SIPClient = app_state["sip_client"]
    voice_client: VoiceClient = app_state["voice_client"]
    agent_manager: AgentManager = app_state["agent_manager"]
    ws_manager: ConnectionManager = app_state["ws_manager"]
    agent_router: AgentRouter = app_state["agent_router"]

    logger.info(f"Eingehender Anruf von: {caller_id} (IP: {remote_ip})")

    # Blacklist pruefen (vor IP-Check, da Blacklist spezifischer ist)
    blacklist_store: BlacklistStore = app_state.get("blacklist_store")
    if blacklist_store and await blacklist_store.is_blacklisted(caller_id):
        logger.warning(f"ABGELEHNT: Anruf von geblockter Nummer {caller_id}")
        await sip_client.reject_call(403)
        await ws_manager.broadcast({
            "type": "call_rejected",
            "caller_id": caller_id,
            "remote_ip": remote_ip,
            "reason": "Nummer auf Blacklist",
        })
        return

    # IP-Whitelist pruefen
    if not is_ip_allowed(remote_ip, caller_id):
        logger.warning(f"ABGELEHNT: Anruf von nicht autorisierter IP {remote_ip}")
        await sip_client.reject_call(403)
        await ws_manager.broadcast({
            "type": "call_rejected",
            "caller_id": caller_id,
            "remote_ip": remote_ip,
            "reason": "IP nicht auf Whitelist",
        })
        return

    # Reset
    _audio_stats["caller_to_ai"] = 0
    _audio_stats["ai_to_caller"] = 0
    _audio_stats["caller_bytes"] = 0
    _audio_stats["ai_bytes"] = 0
    agent_router.clear_history()

    await ws_manager.broadcast({
        "type": "call_incoming",
        "caller_id": caller_id,
    })

    # Agent-Manager: Call starten (aktiviert Default-Agent)
    await agent_manager.start_call(caller_id)

    # Voice Client konfigurieren mit Tools/Instructions vom aktiven Agent
    voice_client.configure_for_agent(
        tools=agent_manager.get_tools(),
        instructions=agent_manager.get_instructions()
    )

    # Anruf annehmen und AI verbinden
    await sip_client.accept_call()
    await voice_client.connect()

    # Begruessung nach kurzer Verzoegerung
    async def delayed_greeting():
        await asyncio.sleep(0.2)
        await voice_client.trigger_greeting()

    asyncio.create_task(delayed_greeting())

    await ws_manager.broadcast({
        "type": "call_active",
        "caller_id": caller_id,
        "agent": agent_manager.active_agent_name,
    })


async def on_audio_from_caller(audio_data: bytes):
    """Audio vom Anrufer empfangen (48kHz) -> AI (16kHz)."""
    voice_client: VoiceClient = app_state["voice_client"]

    _audio_stats["caller_to_ai"] += 1
    _audio_stats["caller_bytes"] += len(audio_data)

    if _audio_stats["caller_to_ai"] % 50 == 1:
        logger.info(
            f"[AUDIO] Caller->AI: {_audio_stats['caller_to_ai']} Pakete, "
            f"{_audio_stats['caller_bytes']} Bytes"
        )

    if voice_client and voice_client.is_connected:
        try:
            resampled = sip_to_ai_input(audio_data)
            await voice_client.send_audio(resampled)
        except Exception as e:
            logger.warning(f"Audio Resample Fehler (Caller->AI): {e}")


async def on_audio_from_ai(audio_data: bytes):
    """Audio von AI empfangen (24kHz) -> Anrufer (48kHz)."""
    sip_client: SIPClient = app_state["sip_client"]

    _audio_stats["ai_to_caller"] += 1
    _audio_stats["ai_bytes"] += len(audio_data)

    if _audio_stats["ai_to_caller"] % 50 == 1:
        logger.info(
            f"[AUDIO] AI->Caller: {_audio_stats['ai_to_caller']} Pakete, "
            f"{_audio_stats['ai_bytes']} Bytes"
        )

    if sip_client and sip_client.is_in_call:
        try:
            resampled = ai_output_to_sip(audio_data)
            await sip_client.send_audio(resampled)
        except Exception as e:
            logger.warning(f"Audio Resample Fehler (AI->Caller): {e}")


async def on_transcript(role: str, text: str, is_final: bool):
    """Transkript-Update von AI."""
    ws_manager: ConnectionManager = app_state["ws_manager"]
    agent_router: AgentRouter = app_state["agent_router"]

    # Transkript an Router fuer Intent-Erkennung
    if is_final and text:
        agent_router.add_transcript(role, text)

    await ws_manager.broadcast({
        "type": "transcript",
        "role": role,
        "text": text,
        "is_final": is_final,
    })


async def on_function_call(call_id: str, name: str, arguments: dict) -> str:
    """Function Call von AI -> Agent-Manager fuehrt Tool aus."""
    agent_manager: AgentManager = app_state["agent_manager"]
    voice_client: VoiceClient = app_state["voice_client"]
    ws_manager: ConnectionManager = app_state["ws_manager"]

    # An GUI senden
    await ws_manager.broadcast({
        "type": "function_call",
        "name": name,
        "arguments": arguments,
    })

    # Agent fuehrt Tool aus
    result = await agent_manager.execute_tool(name, arguments)

    # Pruefen ob das Ergebnis ein Hangup-Signal ist (Security Gate: zu viele Fehlversuche)
    if result and result.startswith("__HANGUP__"):
        sip_client: SIPClient = app_state["sip_client"]
        blacklist_store: BlacklistStore = app_state.get("blacklist_store")
        caller_id = agent_manager._current_caller

        logger.warning(f"Anruf wird beendet (Security Gate): {caller_id}")

        # Fehlgeschlagenen Anruf aufzeichnen und Auto-Blacklist pruefen
        if blacklist_store and caller_id:
            await blacklist_store.record_failed_call(caller_id)
            blacklisted = await blacklist_store.check_and_auto_blacklist(caller_id)
            if blacklisted:
                await ws_manager.broadcast({
                    "type": "blacklist_updated",
                })

        # Auflegen
        if sip_client and sip_client.is_in_call:
            await sip_client.hangup()

        result = "Anruf wird beendet - zu viele fehlgeschlagene Versuche."

        await ws_manager.broadcast({
            "type": "function_result",
            "name": name,
            "result": result,
        })
        return result

    # Pruefen ob das Ergebnis ein Agent-Switch-Signal ist
    if result and result.startswith("__SWITCH__:"):
        target_agent = result.split(":", 1)[1]
        success = await agent_manager.switch_agent(target_agent)
        if success:
            # Security Gate: Wenn von security_agent weggewechselt wird, Anruf freischalten
            if agent_manager.active_agent_name != "security_agent":
                agent_manager.set_call_unlocked(True)

            # OpenAI Session mit neuen Tools/Instructions aktualisieren
            if voice_client and voice_client.is_connected:
                await voice_client.update_session(
                    tools=agent_manager.get_tools(),
                    instructions=agent_manager.get_instructions()
                )
            display = agent_manager.active_agent.display_name if agent_manager.active_agent else target_agent
            result = f"Du bist jetzt verbunden mit: {display}"
            logger.info(f"Agent-Switch via Tool: -> {target_agent}")
        else:
            result = f"Agent-Wechsel zu '{target_agent}' fehlgeschlagen."

    # Ergebnis an GUI
    await ws_manager.broadcast({
        "type": "function_result",
        "name": name,
        "result": result[:200] if result else "",
    })

    return result


async def on_interruption():
    """User hat die AI unterbrochen (Barge-In)."""
    sip_client: SIPClient = app_state["sip_client"]

    if sip_client:
        cleared = sip_client.clear_audio_queue()
        if cleared > 0:
            logger.info(f"[INTERRUPTION] Audio-Queue geleert: {cleared} Frames")


async def on_call_ended(reason: str):
    """Anruf beendet."""
    voice_client: VoiceClient = app_state["voice_client"]
    agent_manager: AgentManager = app_state["agent_manager"]
    ws_manager: ConnectionManager = app_state["ws_manager"]

    logger.info(f"Anruf beendet: {reason}")

    await agent_manager.end_call()
    await voice_client.disconnect()

    await ws_manager.broadcast({
        "type": "call_ended",
        "reason": reason,
    })


async def on_agent_changed(old_agent: str, new_agent: str):
    """Agent wurde gewechselt."""
    ws_manager: ConnectionManager = app_state["ws_manager"]

    await ws_manager.broadcast({
        "type": "agent_changed",
        "old_agent": old_agent,
        "new_agent": new_agent,
    })


# ============== Lifespan ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info("=== VoiceAgent Platform startet ===")

    # Database initialisieren
    db = await get_database()
    await db.initialize()

    # Task-System
    task_store = TaskStore(db)
    task_executor = TaskExecutor(task_store)

    # Blacklist-System
    blacklist_store = BlacklistStore(db)

    # Agent-System
    agent_registry = AgentRegistry()
    agent_registry.discover_agents(settings.AGENTS_DIR)
    logger.info(f"Agenten entdeckt: {agent_registry.count}")

    agent_manager = AgentManager(agent_registry, default_agent="security_agent")
    agent_manager.on_agent_changed = on_agent_changed

    agent_router = AgentRouter(agent_registry)

    # SIP Client
    sip_client = SIPClient()

    # AI Voice Client
    voice_client = VoiceClient()

    # WebSocket Manager
    ws_manager = ConnectionManager()

    # App State zusammenbauen
    app_state.update({
        "db": db,
        "task_store": task_store,
        "task_executor": task_executor,
        "blacklist_store": blacklist_store,
        "agent_registry": agent_registry,
        "agent_manager": agent_manager,
        "agent_router": agent_router,
        "sip_client": sip_client,
        "voice_client": voice_client,
        "ws_manager": ws_manager,
    })

    # MainAgent: Registry injizieren (fuer dynamische Agent-Liste)
    main_agent = agent_registry.get_agent("main_agent")
    if main_agent and hasattr(main_agent, "set_registry"):
        main_agent.set_registry(agent_registry)
        logger.info("AgentRegistry in Main-Agent injiziert")

    # WebSocket-Manager in Code-Agent injizieren (fuer Coding-Progress)
    code_agent = agent_registry.get_agent("code_agent")
    if code_agent and hasattr(code_agent, "set_ws_manager"):
        code_agent.set_ws_manager(ws_manager)
        logger.info("WebSocket-Manager in Code-Agent injiziert")

    # WebSocket-Manager in Ideas-Agent injizieren (fuer Ideen-Updates)
    ideas_agent = agent_registry.get_agent("ideas_agent")
    if ideas_agent and hasattr(ideas_agent, "set_ws_manager"):
        ideas_agent.set_ws_manager(ws_manager)
        logger.info("WebSocket-Manager in Ideas-Agent injiziert")

    # Event Handler verbinden
    sip_client.on_incoming_call = on_incoming_call
    sip_client.on_audio_received = on_audio_from_caller
    sip_client.on_call_ended = on_call_ended

    voice_client.on_audio_response = on_audio_from_ai
    voice_client.on_transcript = on_transcript
    voice_client.on_interruption = on_interruption
    voice_client.on_function_call = on_function_call

    # SIP Client starten
    await sip_client.start()
    logger.info("SIP Client gestartet")

    # Pending Tasks wiederherstellen
    await task_executor.recover_pending()

    logger.info("=== VoiceAgent Platform bereit ===")

    yield

    # Cleanup
    logger.info("Server wird heruntergefahren...")
    await sip_client.stop()
    await voice_client.disconnect()
    await db.close()


# ============== FastAPI App ==============

app = FastAPI(
    title="VoiceAgent Platform API",
    description="Modulare Voice-Agent Plattform mit SIP und OpenAI Realtime API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes registrieren
api_router = setup_routes(app_state)
ws_router = setup_ws_routes(app_state)
app.include_router(api_router)
app.include_router(ws_router)

# ============== Web Dashboard ==============
# Statische Dateien (CSS, JS) und index.html servieren

_web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web")
# Im Docker: /app/web
if not os.path.isdir(_web_dir):
    _web_dir = "/app/web"

if os.path.isdir(_web_dir):
    @app.get("/", include_in_schema=False)
    async def serve_dashboard():
        return FileResponse(os.path.join(_web_dir, "index.html"))

    app.mount("/static", StaticFiles(directory=_web_dir), name="static")
    logger.info(f"Web Dashboard aktiv: {_web_dir}")


# ============== Main ==============

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "core.app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
        log_level="info"
    )
