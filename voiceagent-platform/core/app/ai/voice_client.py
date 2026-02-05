"""
OpenAI Realtime API Client fuer VoiceAgent Platform.

Streamt Audio bidirektional zur OpenAI API via WebSocket.
Tools und Instructions kommen vom aktiven Agent (nicht hardcoded).
"""

import asyncio
import base64
import json
import logging
from typing import Callable, Optional

from core.app.config import settings

logger = logging.getLogger(__name__)

# Verfuegbare OpenAI Realtime Modelle
AVAILABLE_MODELS = [
    "gpt-realtime",
    "gpt-4o-realtime-preview-2024-12-17",
    "gpt-4o-mini-realtime-preview-2024-12-17",
    "gpt-4o-realtime-preview",
]

DEFAULT_MODEL = "gpt-realtime"


class VoiceClient:
    """
    Async Client fuer OpenAI Realtime API via WebSocket.

    Im Gegensatz zum POC werden Tools und Instructions nicht
    hardcoded, sondern vom aktiven Agent bereitgestellt.
    """

    INPUT_SAMPLE_RATE = 16000   # AI erwartet 16kHz
    OUTPUT_SAMPLE_RATE = 24000  # AI sendet 24kHz

    REALTIME_BASE_URL = "wss://api.openai.com/v1/realtime?model="

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self._ws = None
        self._session = None
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None

        self.muted = False
        self._model = DEFAULT_MODEL
        self._response_in_progress = False  # Finding #4: Response-Status tracken

        # Tools und Instructions kommen vom AgentManager
        self._tools: list[dict] = []
        self._instructions: str = ""

        # Event Callbacks
        self.on_audio_response: Optional[Callable[[bytes], None]] = None
        self.on_transcript: Optional[Callable[[str, str, bool], None]] = None
        self.on_interruption: Optional[Callable[[], None]] = None
        self.on_function_call: Optional[Callable[[str, str, dict], None]] = None
        self.on_debug_event: Optional[Callable[[str, dict], None]] = None

    @property
    def model(self) -> str:
        """Aktuelles Modell."""
        return self._model

    def set_model(self, model: str) -> bool:
        """Setzt das Modell (wird beim naechsten Anruf aktiv)."""
        if model in AVAILABLE_MODELS:
            self._model = model
            logger.info(f"Modell geaendert zu: {model}")
            return True
        logger.warning(f"Unbekanntes Modell: {model}")
        return False

    def configure_for_agent(self, tools: list[dict], instructions: str):
        """
        Konfiguriert den Client fuer einen bestimmten Agent.

        Args:
            tools: OpenAI Function-Calling Tool-Definitionen
            instructions: System-Prompt
        """
        self._tools = tools
        self._instructions = instructions
        logger.info(f"VoiceClient konfiguriert: {len(tools)} Tools, {len(instructions)} Zeichen Instructions")

    @property
    def is_connected(self) -> bool:
        """Ist die WebSocket-Verbindung aktiv?"""
        return self._ws is not None and self._running

    async def connect(self):
        """Verbindung zur Realtime API aufbauen."""
        try:
            import aiohttp

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }

            realtime_url = f"{self.REALTIME_BASE_URL}{self._model}"
            logger.info(f"Verbinde zu OpenAI mit Modell: {self._model}")

            session = aiohttp.ClientSession()
            self._ws = await session.ws_connect(realtime_url, headers=headers)
            self._session = session
            self._running = True

            await self._configure_session()

            self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info("OpenAI Realtime API verbunden")

        except Exception as e:
            logger.error(f"OpenAI Verbindung fehlgeschlagen: {e}")
            self._running = False

    async def _configure_session(self):
        """Session mit Instruktionen und Tools konfigurieren."""
        if not self._ws:
            return

        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self._instructions,
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.4,
                    "prefix_padding_ms": 200,
                    "silence_duration_ms": 400,
                    "create_response": True
                },
                "tools": self._tools,
                "tool_choice": "auto"
            }
        }

        await self._ws.send_str(json.dumps(config))
        logger.info(f"Session konfiguriert mit {len(self._tools)} Tools")

    async def update_session(self, tools: list[dict] = None, instructions: str = None):
        """
        Aktualisiert die laufende Session (z.B. bei Agent-Wechsel).

        Args:
            tools: Neue Tool-Definitionen (optional)
            instructions: Neue Instructions (optional)
        """
        if not self._ws or not self._running:
            return

        session_update = {}
        if tools is not None:
            self._tools = tools
            session_update["tools"] = tools
        if instructions is not None:
            self._instructions = instructions
            session_update["instructions"] = instructions

        if session_update:
            config = {
                "type": "session.update",
                "session": session_update
            }
            await self._ws.send_str(json.dumps(config))
            logger.info("Session aktualisiert")

    async def trigger_greeting(self):
        """Loest die initiale Begruessung aus."""
        if not self._ws or not self._running:
            return

        if self._response_in_progress:
            logger.warning("[OpenAI] Response bereits aktiv - Greeting uebersprungen")
            return

        try:
            self._response_in_progress = True
            await self._ws.send_str(json.dumps({
                "type": "response.create"
            }))
            logger.info("[OpenAI] Begruessung ausgeloest")
        except Exception as e:
            self._response_in_progress = False
            logger.error(f"Fehler beim Ausloesen der Begruessung: {e}")

    async def _receive_loop(self):
        """Empfaengt Events von der Realtime API."""
        if not self._ws:
            return

        try:
            async for msg in self._ws:
                if not self._running:
                    break

                if msg.type == 1:  # TEXT
                    try:
                        event = json.loads(msg.data)
                        await self._handle_event(event)
                    except json.JSONDecodeError:
                        logger.warning("Ungueltiges JSON von API")
                elif msg.type == 258:  # CLOSED
                    break
                elif msg.type == 256:  # ERROR
                    logger.error(f"WebSocket Fehler: {msg.data}")
                    break

        except Exception as e:
            logger.error(f"Receive Loop Fehler: {e}")
        finally:
            self._running = False

    async def _handle_event(self, event: dict):
        """Verarbeitet ein Event von der API."""
        event_type = event.get("type", "")

        # Log alle Events (ausser audio.delta wegen Menge)
        if event_type not in ["response.audio.delta"]:
            logger.info(f"[OpenAI Event] {event_type}")
            if "function" in event_type or "tool" in event_type:
                logger.info(f"[OpenAI Event Details] {json.dumps(event, ensure_ascii=False)[:500]}")

            if self.on_debug_event:
                await self.on_debug_event(event_type, event)

        # --- Response Lifecycle Tracking (Finding #4) ---
        if event_type == "response.created":
            self._response_in_progress = True

        elif event_type == "response.done":
            self._response_in_progress = False

        # --- Audio Events ---
        elif event_type == "response.audio.delta":
            audio_b64 = event.get("delta", "")
            if audio_b64 and not self.muted:
                audio_bytes = base64.b64decode(audio_b64)

                if not hasattr(self, '_audio_chunk_count'):
                    self._audio_chunk_count = 0
                self._audio_chunk_count += 1
                if self._audio_chunk_count == 1:
                    logger.info(f"[OpenAI] Erstes Audio-Chunk empfangen, size={len(audio_bytes)}")

                if self.on_audio_response:
                    await self.on_audio_response(audio_bytes)

        # --- Speech Detection ---
        elif event_type == "input_audio_buffer.speech_started":
            logger.info("[OpenAI] Sprache erkannt - Interruption")
            self._response_in_progress = False  # Interruption beendet laufende Response
            if self.on_interruption:
                await self.on_interruption()

        elif event_type == "input_audio_buffer.speech_stopped":
            logger.info("[OpenAI] Sprache beendet")

        # --- Transcription ---
        elif event_type == "conversation.item.input_audio_transcription.completed":
            text = event.get("transcript", "")
            if text and self.on_transcript:
                await self.on_transcript("caller", text, True)

        elif event_type == "response.audio_transcript.delta":
            text = event.get("delta", "")
            if text and self.on_transcript:
                await self.on_transcript("assistant", text, False)

        elif event_type == "response.audio_transcript.done":
            text = event.get("transcript", "")
            if text and self.on_transcript:
                await self.on_transcript("assistant", text, True)

        # --- Errors ---
        elif event_type == "error":
            error = event.get("error", {})
            logger.error(f"[OpenAI] API Error: {error}")
            # Bei Error ist die Response auch nicht mehr aktiv
            if "already has an active response" in str(error):
                logger.warning("[OpenAI] Response war noch aktiv - warte auf Abschluss")
            else:
                self._response_in_progress = False

        # --- Function Calls ---
        elif event_type == "response.function_call_arguments.done":
            await self._handle_function_call(event)

    async def _handle_function_call(self, event: dict):
        """
        Function Call empfangen - an den AgentManager delegieren.

        Args:
            event: Das function_call_arguments.done Event
        """
        call_id = event.get("call_id", "")
        name = event.get("name", "")
        arguments_str = event.get("arguments", "{}")

        logger.info(f"[OpenAI] Function Call: {name}({arguments_str})")

        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            arguments = {}

        # Callback zum AgentManager - der fuehrt das Tool aus
        if self.on_function_call:
            result = await self.on_function_call(call_id, name, arguments)
        else:
            result = f"Fehler: Kein Handler fuer Function Call '{name}'"

        # Ergebnis an OpenAI senden
        await self._send_function_result(call_id, result)

    async def _send_function_result(self, call_id: str, result: str):
        """Sendet das Ergebnis einer Function an OpenAI."""
        if not self._ws or not self._running:
            return

        try:
            # 1. Function Output senden
            output_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result
                }
            }
            await self._ws.send_str(json.dumps(output_event))

            # 2. Neue Response anfordern (nur wenn keine aktiv ist)
            if self._response_in_progress:
                logger.info(
                    f"[OpenAI] Response noch aktiv - warte vor response.create "
                    f"(call_id={call_id})"
                )
                # Kurz warten bis die vorherige Response fertig ist
                for _ in range(50):  # Max 5 Sekunden warten
                    await asyncio.sleep(0.1)
                    if not self._response_in_progress:
                        break

            self._response_in_progress = True
            response_event = {"type": "response.create"}
            await self._ws.send_str(json.dumps(response_event))

            logger.info(f"[OpenAI] Function Ergebnis gesendet fuer call_id={call_id}")

        except Exception as e:
            self._response_in_progress = False
            logger.error(f"Fehler beim Senden des Function-Ergebnisses: {e}")

    async def send_audio(self, audio_data: bytes):
        """
        Audio an die API senden.

        Args:
            audio_data: PCM16 Audio @ 16kHz
        """
        if not self._ws or not self._running:
            return

        try:
            if not hasattr(self, '_sent_audio_count'):
                self._sent_audio_count = 0
            self._sent_audio_count += 1

            if self._sent_audio_count == 1:
                logger.info(f"[OpenAI] Erstes Audio gesendet: {len(audio_data)} bytes")

            audio_b64 = base64.b64encode(audio_data).decode('utf-8')

            await self._ws.send_str(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": audio_b64
            }))

        except Exception as e:
            logger.warning(f"Audio senden Fehler: {e}")

    async def disconnect(self):
        """Verbindung trennen."""
        self._running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

        # Reset state (Finding #14)
        self._audio_chunk_count = 0
        self._sent_audio_count = 0
        self._response_in_progress = False

        logger.info("OpenAI Realtime API getrennt")
