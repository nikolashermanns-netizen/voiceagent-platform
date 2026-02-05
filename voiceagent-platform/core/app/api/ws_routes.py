"""
WebSocket Routes fuer VoiceAgent Platform.

Live-Updates fuer Dashboard/GUI:
- Transkript
- Call-Events
- Task-Updates
- Agent-Status
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_ws_routes(app_state):
    """
    Erstellt die WebSocket-Routes mit Zugriff auf den App-State.

    Args:
        app_state: Dict mit sip_client, voice_client, ws_manager, etc.
    """

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket fuer Live-Updates an die GUI.

        Sendet:
        - call_incoming: Neuer eingehender Anruf
        - call_active: Anruf aktiv
        - call_ended: Anruf beendet
        - transcript: Transkript-Updates
        - task_update: Task-Status-Aenderung
        - agent_changed: Agent gewechselt
        - firewall_status: Firewall-Status
        """
        ws_manager: ConnectionManager = app_state.get("ws_manager")
        if not ws_manager:
            await websocket.close()
            return

        await ws_manager.connect(websocket)

        # Initial Status senden
        sip = app_state.get("sip_client")
        agent_mgr = app_state.get("agent_manager")

        await websocket.send_json({
            "type": "status",
            "sip_registered": sip.is_registered if sip else False,
            "call_active": sip.is_in_call if sip else False,
            "active_agent": agent_mgr.active_agent_name if agent_mgr else None,
            "available_agents": agent_mgr.registry.get_agent_names() if agent_mgr else [],
        })

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "accept_call":
                    if sip and sip.has_incoming_call:
                        await sip.accept_call()

                elif msg_type == "hangup":
                    if sip and sip.is_in_call:
                        await sip.hangup()

                elif msg_type == "mute_ai":
                    voice = app_state.get("voice_client")
                    if voice:
                        voice.muted = True

                elif msg_type == "unmute_ai":
                    voice = app_state.get("voice_client")
                    if voice:
                        voice.muted = False

                elif msg_type == "switch_agent":
                    agent_name = data.get("agent_name")
                    if agent_mgr and agent_name:
                        success = await agent_mgr.switch_agent(agent_name)
                        if success:
                            voice = app_state.get("voice_client")
                            if voice and voice.is_connected:
                                await voice.update_session(
                                    tools=agent_mgr.get_tools(),
                                    instructions=agent_mgr.get_instructions()
                                )

        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
            logger.info("Client disconnected")

    return router
