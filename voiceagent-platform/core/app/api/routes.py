"""
REST API Routes fuer VoiceAgent Platform.

Bietet Endpoints fuer Status, Konfiguration, Call-Control,
Tasks, Agents und Firewall.
"""

import ipaddress
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from core.app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ============== IP Whitelist fuer SIP ==============
ALLOWED_SIP_NETWORKS = [
    ipaddress.ip_network("217.10.0.0/16"),       # Sipgate Hauptnetz
    ipaddress.ip_network("212.9.32.0/19"),        # Sipgate Infrastruktur
    ipaddress.ip_network("95.174.128.0/20"),      # Sipgate zusaetzlich
    ipaddress.ip_network("2001:ab7::/32"),        # Sipgate IPv6
]

PRIVATE_IP_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

# Firewall Status
sip_firewall_enabled = True


def is_ip_allowed(ip_str: str, caller_uri: str = None) -> bool:
    """Prueft ob eine IP-Adresse von einem erlaubten SIP-Provider stammt."""
    global sip_firewall_enabled

    if not sip_firewall_enabled:
        return True

    if not ip_str:
        return False

    try:
        ip = ipaddress.ip_address(ip_str)

        for network in ALLOWED_SIP_NETWORKS:
            if ip in network:
                return True

        # Private IP: Erlauben wenn Caller-URI passend
        if any(ip in net for net in PRIVATE_IP_NETWORKS):
            if caller_uri and (
                settings.SIP_PUBLIC_IP in caller_uri
                or "sipgate" in caller_uri.lower()
            ):
                return True

        return False
    except ValueError:
        return False


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """API-Key Authentifizierung (optional, wenn API_KEY gesetzt)."""
    if settings.API_KEY and settings.API_KEY != "":
        if x_api_key != settings.API_KEY:
            raise HTTPException(status_code=401, detail="Ungueltiger API-Key")


def setup_routes(app_state):
    """
    Erstellt die API-Routes mit Zugriff auf den App-State.

    Args:
        app_state: Dict mit sip_client, voice_client, agent_manager, etc.
    """

    @router.get("/health")
    async def health():
        """Health check."""
        sip = app_state.get("sip_client")
        return {
            "status": "running",
            "sip_registered": sip.is_registered if sip else False,
            "call_active": sip.is_in_call if sip else False,
        }

    @router.get("/status")
    async def get_status():
        """Detaillierter Status."""
        sip = app_state.get("sip_client")
        voice = app_state.get("voice_client")
        agent_mgr = app_state.get("agent_manager")
        task_exec = app_state.get("task_executor")

        return {
            "sip": {
                "registered": sip.is_registered if sip else False,
                "server": settings.SIP_SERVER,
                "user": settings.SIP_USER,
                "in_call": sip.is_in_call if sip else False,
                "caller_id": sip.current_caller_id if sip else None,
            },
            "ai": {
                "connected": voice.is_connected if voice else False,
                "model": voice.model if voice else "",
            },
            "agent": {
                "active": agent_mgr.active_agent_name if agent_mgr else None,
                "available": agent_mgr.registry.get_agent_names() if agent_mgr else [],
            },
            "tasks": {
                "active": task_exec.active_count if task_exec else 0,
            },
            "firewall": {
                "enabled": sip_firewall_enabled,
            },
        }

    # ============== Call Control ==============

    @router.post("/call/accept")
    async def accept_call():
        """Anruf annehmen."""
        sip = app_state.get("sip_client")
        if sip and sip.has_incoming_call:
            await sip.accept_call()
            return {"status": "accepted"}
        return {"status": "no_incoming_call"}

    @router.post("/call/hangup")
    async def hangup_call():
        """Anruf beenden."""
        sip = app_state.get("sip_client")
        if sip and sip.is_in_call:
            await sip.hangup()
            return {"status": "hungup"}
        return {"status": "no_active_call"}

    @router.post("/ai/mute")
    async def mute_ai():
        """AI stumm schalten."""
        voice = app_state.get("voice_client")
        if voice:
            voice.muted = True
            return {"status": "muted"}
        return {"status": "error"}

    @router.post("/ai/unmute")
    async def unmute_ai():
        """AI Stummschaltung aufheben."""
        voice = app_state.get("voice_client")
        if voice:
            voice.muted = False
            return {"status": "unmuted"}
        return {"status": "error"}

    # ============== Model ==============

    @router.get("/model")
    async def get_model():
        """Aktuelles AI-Modell abrufen."""
        voice = app_state.get("voice_client")
        return {
            "model": voice.model if voice else "",
            "available_models": AVAILABLE_MODELS,
        }

    @router.post("/model")
    async def set_model(data: dict):
        """AI-Modell setzen."""
        voice = app_state.get("voice_client")
        if voice:
            model = data.get("model", "")
            if voice.set_model(model):
                return {"status": "ok", "model": model}
            return {"status": "error", "message": "Unbekanntes Modell"}
        return {"status": "error"}

    # ============== Agents ==============

    @router.get("/agents")
    async def get_agents():
        """Alle verfuegbaren Agenten abrufen."""
        agent_mgr = app_state.get("agent_manager")
        if agent_mgr:
            return {
                "agents": agent_mgr.registry.get_agent_info(),
                "active": agent_mgr.active_agent_name,
            }
        return {"agents": [], "active": None}

    @router.post("/agents/switch")
    async def switch_agent(data: dict):
        """Aktiven Agent wechseln."""
        agent_mgr = app_state.get("agent_manager")
        if agent_mgr:
            agent_name = data.get("agent_name", "")
            success = await agent_mgr.switch_agent(agent_name)
            if success:
                # Voice Client Session aktualisieren
                voice = app_state.get("voice_client")
                if voice and voice.is_connected:
                    await voice.update_session(
                        tools=agent_mgr.get_tools(),
                        instructions=agent_mgr.get_instructions()
                    )
                return {"status": "ok", "agent": agent_name}
            return {"status": "error", "message": f"Agent '{agent_name}' nicht gefunden"}
        return {"status": "error"}

    # ============== Tasks ==============

    @router.get("/tasks")
    async def get_tasks():
        """Alle Tasks abrufen."""
        task_store = app_state.get("task_store")
        if task_store:
            tasks = await task_store.get_all()
            return {"tasks": [t.model_dump() for t in tasks]}
        return {"tasks": []}

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str):
        """Einzelnen Task abrufen."""
        task_store = app_state.get("task_store")
        if task_store:
            task = await task_store.get(task_id)
            if task:
                return task.model_dump()
            raise HTTPException(status_code=404, detail="Task nicht gefunden")
        return {"error": "Task Store nicht verfuegbar"}

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str):
        """Task abbrechen."""
        task_exec = app_state.get("task_executor")
        if task_exec:
            task = await task_exec.cancel(task_id)
            if task:
                return {"status": "cancelled", "task": task.model_dump()}
            raise HTTPException(status_code=404, detail="Task nicht gefunden")
        return {"error": "Task Executor nicht verfuegbar"}

    # ============== Ideas ==============

    @router.get("/ideas")
    async def get_ideas(category: str = None, status: str = None):
        """Alle Ideen abrufen, optional nach Kategorie/Status gefiltert."""
        from agents.ideas_agent.idea_store import IdeaStore
        db = app_state.get("db")
        if not db:
            return {"ideas": []}
        store = IdeaStore(db)
        ideas = await store.get_all(category=category, status=status)
        return {"ideas": [idea.to_dict() for idea in ideas]}

    @router.get("/ideas/{idea_id}")
    async def get_idea(idea_id: str):
        """Einzelne Idee abrufen."""
        from agents.ideas_agent.idea_store import IdeaStore
        db = app_state.get("db")
        if not db:
            raise HTTPException(status_code=500, detail="Datenbank nicht verfuegbar")
        store = IdeaStore(db)
        idea = await store.get(idea_id)
        if not idea:
            raise HTTPException(status_code=404, detail="Idee nicht gefunden")
        return idea.to_dict()

    @router.put("/ideas/{idea_id}/archive")
    async def archive_idea(idea_id: str):
        """Idee archivieren (nicht loeschen!)."""
        from agents.ideas_agent.idea_store import IdeaStore
        db = app_state.get("db")
        if not db:
            raise HTTPException(status_code=500, detail="Datenbank nicht verfuegbar")
        store = IdeaStore(db)
        idea = await store.archive(idea_id)
        if not idea:
            raise HTTPException(status_code=404, detail="Idee nicht gefunden")

        ws_manager = app_state.get("ws_manager")
        if ws_manager:
            await ws_manager.broadcast({
                "type": "idea_update",
                "action": "archived",
                "idea": idea.to_dict(),
            })

        return idea.to_dict()

    # ============== Projects ==============

    @router.get("/projects")
    async def get_projects(status: str = None):
        """Alle Projekte abrufen."""
        from agents.ideas_agent.project_planner import ProjectPlanner
        db = app_state.get("db")
        if not db:
            return {"projects": []}
        planner = ProjectPlanner(db)
        projects = await planner.get_all(status=status)
        return {"projects": [p.to_dict() for p in projects]}

    @router.get("/projects/{project_id}")
    async def get_project(project_id: str):
        """Einzelnes Projekt abrufen."""
        from agents.ideas_agent.project_planner import ProjectPlanner
        db = app_state.get("db")
        if not db:
            raise HTTPException(status_code=500, detail="Datenbank nicht verfuegbar")
        planner = ProjectPlanner(db)
        project = await planner.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        return project.to_dict()

    # ============== Call History ==============

    @router.get("/calls/history")
    async def get_call_history():
        """Vergangene Anrufer (distinct, neueste zuerst)."""
        db = app_state.get("db")
        if not db:
            return {"entries": []}
        entries = await db.fetch_all(
            """SELECT caller_id,
                      MAX(started_at) as last_call,
                      COUNT(*) as call_count
               FROM calls
               WHERE caller_id IS NOT NULL
               GROUP BY caller_id
               ORDER BY MAX(started_at) DESC
               LIMIT 50"""
        )
        return {"entries": entries}

    # ============== Blacklist ==============

    @router.get("/blacklist")
    async def get_blacklist():
        """Alle geblockten Nummern abrufen."""
        blacklist_store = app_state.get("blacklist_store")
        if blacklist_store:
            entries = await blacklist_store.get_all()
            return {"entries": entries}
        return {"entries": []}

    @router.post("/blacklist")
    async def add_to_blacklist(data: dict):
        """Nummer zur Blacklist hinzufuegen."""
        blacklist_store = app_state.get("blacklist_store")
        if blacklist_store:
            caller_id = data.get("caller_id", "").strip()
            if not caller_id:
                raise HTTPException(status_code=400, detail="caller_id fehlt")
            reason = data.get("reason", "Manuell hinzugefuegt")
            await blacklist_store.add(caller_id, reason)
            ws_manager = app_state.get("ws_manager")
            if ws_manager:
                await ws_manager.broadcast({"type": "blacklist_updated"})
            return {"status": "ok", "caller_id": caller_id}
        return {"status": "error"}

    @router.delete("/blacklist/{caller_id:path}")
    async def remove_from_blacklist(caller_id: str):
        """Nummer von der Blacklist entfernen."""
        blacklist_store = app_state.get("blacklist_store")
        if blacklist_store:
            removed = await blacklist_store.remove(caller_id)
            if removed:
                ws_manager = app_state.get("ws_manager")
                if ws_manager:
                    await ws_manager.broadcast({"type": "blacklist_updated"})
                return {"status": "ok", "removed": caller_id}
            raise HTTPException(status_code=404, detail="Nummer nicht auf Blacklist")
        return {"status": "error"}

    # ============== Whitelist ==============

    @router.get("/whitelist")
    async def get_whitelist():
        """Alle Whitelist-Nummern abrufen."""
        blacklist_store = app_state.get("blacklist_store")
        if blacklist_store:
            entries = await blacklist_store.get_all_whitelist()
            return {"entries": entries}
        return {"entries": []}

    @router.post("/whitelist")
    async def add_to_whitelist(data: dict):
        """Nummer zur Whitelist hinzufuegen."""
        blacklist_store = app_state.get("blacklist_store")
        if blacklist_store:
            caller_id = data.get("caller_id", "").strip()
            if not caller_id:
                raise HTTPException(status_code=400, detail="caller_id fehlt")
            note = data.get("note", "")
            await blacklist_store.add_to_whitelist(caller_id, note)
            ws_manager = app_state.get("ws_manager")
            if ws_manager:
                await ws_manager.broadcast({"type": "whitelist_updated"})
            return {"status": "ok", "caller_id": caller_id}
        return {"status": "error"}

    @router.delete("/whitelist/{caller_id:path}")
    async def remove_from_whitelist(caller_id: str):
        """Nummer von der Whitelist entfernen."""
        blacklist_store = app_state.get("blacklist_store")
        if blacklist_store:
            removed = await blacklist_store.remove_from_whitelist(caller_id)
            if removed:
                ws_manager = app_state.get("ws_manager")
                if ws_manager:
                    await ws_manager.broadcast({"type": "whitelist_updated"})
                return {"status": "ok", "removed": caller_id}
            raise HTTPException(status_code=404, detail="Nummer nicht auf Whitelist")
        return {"status": "error"}

    # ============== Firewall ==============

    @router.get("/firewall")
    async def get_firewall_status():
        """SIP Firewall Status."""
        return {
            "enabled": sip_firewall_enabled,
            "allowed_networks": [str(n) for n in ALLOWED_SIP_NETWORKS],
        }

    @router.post("/firewall")
    async def set_firewall_status(data: dict):
        """SIP Firewall aktivieren/deaktivieren."""
        global sip_firewall_enabled

        enabled = data.get("enabled")
        if enabled is None:
            return {"status": "error", "message": "Parameter 'enabled' fehlt"}

        sip_firewall_enabled = bool(enabled)
        logger.info(
            f"SIP Firewall {'aktiviert' if sip_firewall_enabled else 'DEAKTIVIERT'}"
        )

        ws_manager = app_state.get("ws_manager")
        if ws_manager:
            await ws_manager.broadcast({
                "type": "firewall_status",
                "enabled": sip_firewall_enabled,
            })

        return {"status": "ok", "enabled": sip_firewall_enabled}

    return router


# Model-Import fuer direkten Zugriff
from core.app.ai.voice_client import AVAILABLE_MODELS
