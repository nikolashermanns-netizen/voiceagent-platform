"""
PJSIP-basierter SIP Client fuer VoiceAgent Platform.

Verwendet pjsua2 fuer professionelle SIP/RTP Unterstuetzung.
Alle PJSIP-Operationen laufen in einem dedizierten Thread.
"""

import asyncio
import logging
import queue
import threading
from typing import Callable, Optional
from collections import deque

from core.app.config import settings

logger = logging.getLogger(__name__)

try:
    import pjsua2 as pj
    PJSUA2_AVAILABLE = True
except ImportError:
    PJSUA2_AVAILABLE = False
    logger.warning("pjsua2 nicht verfuegbar - SIP Client deaktiviert")


class AudioMediaPort(pj.AudioMediaPort if PJSUA2_AVAILABLE else object):
    """
    Custom Audio Media Port fuer bidirektionales Audio-Streaming.

    Empfaengt Audio vom Anrufer und sendet Audio zur AI.
    Empfaengt Audio von der AI und sendet es zum Anrufer.
    """

    def __init__(self, name: str = "AIBridge"):
        if PJSUA2_AVAILABLE:
            super().__init__()
        self.name = name

        # Queues fuer Audio-Austausch
        # 1000 Frames = 20 Sekunden Audio @ 20ms/Frame
        self._outgoing_queue: deque = deque(maxlen=1000)  # AI -> Caller
        self._incoming_callback: Optional[Callable] = None  # Caller -> AI

        # Audio Format Info (wird beim Erstellen gesetzt)
        self._clock_rate = settings.SAMPLE_RATE_SIP  # 48000 Opus default
        self._channel_count = 1
        self._samples_per_frame = 960  # 20ms @ 48kHz
        self._bits_per_sample = 16

        # Audio Buffer fuer Frame-Splitting
        self._audio_buffer = b''

        # Statistics
        self._rx_frame_count = 0
        self._tx_frame_count = 0
        self._tx_audio_count = 0  # Frames with actual audio (not silence)

    def createPort(self, clock_rate: int, channel_count: int,
                   samples_per_frame: int, bits_per_sample: int):
        """Erstellt den Audio Port mit den gegebenen Parametern."""
        if not PJSUA2_AVAILABLE:
            return

        self._clock_rate = clock_rate
        self._channel_count = channel_count
        self._samples_per_frame = samples_per_frame
        self._bits_per_sample = bits_per_sample

        # PJSIP AudioMediaPortInfo erstellen
        fmt = pj.MediaFormatAudio()
        fmt.type = pj.PJMEDIA_TYPE_AUDIO
        fmt.clockRate = clock_rate
        fmt.channelCount = channel_count
        fmt.bitsPerSample = bits_per_sample
        fmt.frameTimeUsec = int((samples_per_frame * 1000000) / clock_rate)

        super().createPort(self.name, fmt)

        logger.info(
            f"AudioMediaPort erstellt: {clock_rate}Hz, {channel_count}ch, "
            f"{samples_per_frame} samples/frame"
        )

    def onFrameRequested(self, frame):
        """
        PJSIP ruft diese Methode auf wenn ein Audio-Frame benoetigt wird (TX zum Anrufer).
        Wir liefern Audio aus der outgoing_queue (von der AI).
        """
        self._tx_frame_count += 1

        try:
            if self._outgoing_queue:
                audio_data = self._outgoing_queue.popleft()
                frame.type = pj.PJMEDIA_FRAME_TYPE_AUDIO
                frame.buf = pj.ByteVector(list(audio_data))
                self._tx_audio_count += 1

                if self._tx_audio_count == 1:
                    logger.info(f"[TX] Erstes AI-Audio Frame gesendet, size={len(audio_data)}")
            else:
                # Stille senden wenn keine Daten verfuegbar
                if not hasattr(self, '_silence_vector'):
                    self._silence_vector = pj.ByteVector([0] * (self._samples_per_frame * 2))
                frame.type = pj.PJMEDIA_FRAME_TYPE_AUDIO
                frame.buf = self._silence_vector

            if self._tx_frame_count % 100 == 0:
                logger.info(
                    f"[TX] Frames: {self._tx_frame_count}, Audio: {self._tx_audio_count}, "
                    f"Queue: {len(self._outgoing_queue)}"
                )

        except Exception as e:
            logger.warning(f"onFrameRequested Error: {e}")
            frame.type = pj.PJMEDIA_FRAME_TYPE_NONE

    def onFrameReceived(self, frame):
        """
        PJSIP ruft diese Methode auf wenn ein Audio-Frame empfangen wurde (RX vom Anrufer).
        Wir leiten es an die AI weiter.
        """
        try:
            if frame.type == pj.PJMEDIA_FRAME_TYPE_AUDIO:
                self._rx_frame_count += 1

                if self._rx_frame_count == 1:
                    logger.info(
                        f"[RX] Erstes Audio-Frame empfangen, "
                        f"size={len(frame.buf) if frame.buf else 0}"
                    )

                if self._rx_frame_count % 100 == 0:
                    logger.info(
                        f"[RX] Frames: {self._rx_frame_count}, "
                        f"buf_size={len(frame.buf) if frame.buf else 0}"
                    )

                if self._incoming_callback and frame.buf:
                    self._incoming_callback(bytes(frame.buf))
        except Exception as e:
            logger.warning(f"onFrameReceived Error: {e}")

    def queue_audio(self, audio_data: bytes):
        """
        Audio zur Wiedergabe an den Anrufer einreihen.
        Teilt das Audio in 20ms Frames auf (960 samples @ 48kHz = 1920 bytes).
        """
        frame_size = self._samples_per_frame * 2  # 1920 bytes

        self._audio_buffer += audio_data

        frames_queued = 0
        while len(self._audio_buffer) >= frame_size:
            frame = self._audio_buffer[:frame_size]
            self._audio_buffer = self._audio_buffer[frame_size:]
            self._outgoing_queue.append(frame)
            frames_queued += 1

        if frames_queued > 10:
            logger.debug(
                f"[TX] {frames_queued} Frames eingereiht, "
                f"Buffer: {len(self._audio_buffer)} bytes"
            )

        queue_len = len(self._outgoing_queue)
        if queue_len == 500:
            logger.warning(f"[TX] Audio Queue halb voll: {queue_len}/1000 Frames")

    def set_incoming_callback(self, callback: Callable):
        """Callback fuer eingehendes Audio (vom Anrufer) setzen."""
        self._incoming_callback = callback

    def clear_queue(self) -> int:
        """Leert die Audio-Queue (fuer Barge-In/Interruption)."""
        count = len(self._outgoing_queue)
        self._outgoing_queue.clear()
        self._audio_buffer = b''
        return count


class CallCallback(pj.Call if PJSUA2_AVAILABLE else object):
    """Callback Handler fuer SIP Calls."""

    def __init__(self, account, call_id: int = -1):
        if PJSUA2_AVAILABLE:
            if call_id == -1:
                call_id = pj.PJSUA_INVALID_ID
            super().__init__(account, call_id)
        self.on_state_changed: Optional[Callable] = None
        self.on_media_state: Optional[Callable] = None
        self.audio_media_port: Optional[AudioMediaPort] = None

    def onCallState(self, prm):
        """Call State geaendert."""
        ci = self.getInfo()
        logger.info(f"Call State: {ci.stateText}")
        if self.on_state_changed:
            self.on_state_changed(ci.state, ci.stateText)

    def onCallMediaState(self, prm):
        """Media State geaendert - Audio-Verbindung herstellen."""
        ci = self.getInfo()
        for i, mi in enumerate(ci.media):
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                logger.info(f"Audio Media aktiv (Index {i})")

                try:
                    call_audio = self.getAudioMedia(i)

                    # Tatsaechlichen Codec loggen
                    try:
                        port_info = call_audio.getPortInfo()
                        logger.info(
                            f"Negotiated Audio: {port_info.format.clockRate}Hz, "
                            f"{port_info.format.channelCount}ch, "
                            f"{port_info.format.bitsPerSample}bit"
                        )
                    except Exception as e:
                        logger.debug(f"Konnte Port-Info nicht lesen: {e}")

                    if self.audio_media_port:
                        call_audio.startTransmit(self.audio_media_port)
                        self.audio_media_port.startTransmit(call_audio)
                        logger.info("Audio-Bridge verbunden: Call <-> AI")
                except Exception as e:
                    logger.error(f"Audio-Verbindung fehlgeschlagen: {e}")

                if self.on_media_state:
                    self.on_media_state()


class AccountCallback(pj.Account if PJSUA2_AVAILABLE else object):
    """Callback Handler fuer SIP Account."""

    def __init__(self):
        if PJSUA2_AVAILABLE:
            super().__init__()
        self.on_incoming_call: Optional[Callable] = None
        self.on_reg_state: Optional[Callable] = None
        self.current_call: Optional[CallCallback] = None

    def onRegState(self, prm):
        """Registration State geaendert."""
        info = self.getInfo()
        is_registered = info.regStatus == 200
        logger.info(f"Registration: {info.regStatusText} ({info.regStatus})")
        if self.on_reg_state:
            self.on_reg_state(is_registered)

    def onIncomingCall(self, prm):
        """Eingehender Anruf."""
        call = CallCallback(self, prm.callId)
        ci = call.getInfo()

        # Remote IP aus remoteContact extrahieren
        remote_ip = None
        remote_contact = ci.remoteContact
        try:
            import re
            match = re.search(r'@([\d\.]+)', remote_contact)
            if match:
                remote_ip = match.group(1)
        except Exception as e:
            logger.warning(f"Konnte Remote-IP nicht extrahieren: {e}")

        logger.info(f"Eingehender Anruf von: {ci.remoteUri} (IP: {remote_ip})")
        self.current_call = call
        if self.on_incoming_call:
            self.on_incoming_call(ci.remoteUri, call, remote_ip)


class SIPClient:
    """
    Async SIP Client basierend auf PJSIP.
    Alle PJSIP-Operationen laufen in einem dedizierten Thread.
    """

    def __init__(self):
        self.server = settings.SIP_SERVER
        self.port = settings.SIP_PORT
        self.user = settings.SIP_USER
        self.password = settings.SIP_PASSWORD
        self.public_ip = settings.SIP_PUBLIC_IP

        self._endpoint = None
        self._account: Optional[AccountCallback] = None
        self._audio_port: Optional[AudioMediaPort] = None

        self._running = False
        self._pjsip_thread: Optional[threading.Thread] = None
        self._command_queue: queue.Queue = queue.Queue()
        self._registered = False
        self._in_call = False
        self._current_caller = None
        self._current_remote_ip = None

        # Event Callbacks (thread-safe via asyncio.Queue)
        self._event_queue: asyncio.Queue = None
        self._loop: asyncio.AbstractEventLoop = None

        # Public callbacks
        self.on_incoming_call: Optional[Callable] = None
        self.on_audio_received: Optional[Callable] = None
        self.on_call_ended: Optional[Callable] = None

    @property
    def is_registered(self) -> bool:
        return self._registered

    @property
    def is_in_call(self) -> bool:
        return self._in_call

    @property
    def has_incoming_call(self) -> bool:
        return self._account is not None and self._account.current_call is not None

    @property
    def current_caller_id(self) -> Optional[str]:
        return self._current_caller

    @property
    def current_remote_ip(self) -> Optional[str]:
        return self._current_remote_ip

    async def start(self):
        """SIP Client starten."""
        if not PJSUA2_AVAILABLE:
            logger.error("pjsua2 nicht installiert!")
            return

        self._loop = asyncio.get_event_loop()
        self._event_queue = asyncio.Queue()
        self._running = True

        # PJSIP Thread starten
        self._pjsip_thread = threading.Thread(target=self._run_pjsip, daemon=True)
        self._pjsip_thread.start()

        # Event Processor starten
        asyncio.create_task(self._process_events())

        # Warten auf Registrierung
        for _ in range(50):
            await asyncio.sleep(0.1)
            if self._registered:
                logger.info("SIP Client registriert und bereit")
                return

        logger.warning("SIP Registrierung dauert laenger als erwartet...")

    def _run_pjsip(self):
        """PJSIP Event Loop (laeuft in eigenem Thread)."""
        try:
            ep_cfg = pj.EpConfig()
            ep_cfg.uaConfig.threadCnt = 0
            ep_cfg.uaConfig.mainThreadOnly = False
            ep_cfg.logConfig.level = 4
            ep_cfg.logConfig.consoleLevel = 4

            # STUN Server fuer NAT-Traversal
            ep_cfg.uaConfig.stunServer.append("stun.sipgate.de")
            ep_cfg.uaConfig.stunServer.append("stun.l.google.com:19302")

            # Media Config - RTP Port Range
            ep_cfg.medConfig.rxDropPct = 0
            ep_cfg.medConfig.txDropPct = 0
            ep_cfg.medConfig.clockRate = 48000  # Konferenz-Bridge Clock Rate
            ep_cfg.medConfig.sndClockRate = 0
            ep_cfg.medConfig.channelCount = 1

            self._endpoint = pj.Endpoint()
            self._endpoint.libCreate()
            self._endpoint.libInit(ep_cfg)

            # UDP Transport mit oeffentlicher IP fuer NAT
            tp_cfg = pj.TransportConfig()
            tp_cfg.port = self.port
            # RTP Port Range explizit setzen (muss mit Firewall uebereinstimmen)
            tp_cfg.portRange = 100  # 5060-5160 fuer SIP Transport

            if self.public_ip:
                tp_cfg.publicAddress = self.public_ip
                logger.info(f"Transport: Public IP={self.public_ip}, Port={self.port}")
            else:
                logger.warning("WARNUNG: SIP_PUBLIC_IP nicht gesetzt! NAT wird nicht funktionieren.")

            self._endpoint.transportCreate(pj.PJSIP_TRANSPORT_UDP, tp_cfg)

            self._configure_codecs()
            self._endpoint.libStart()

            # Null Sound Device (keine echte Audio-Hardware noetig)
            try:
                self._endpoint.audDevManager().setNullDev()
                logger.info("Null Sound Device aktiviert")
            except Exception as e:
                logger.warning(f"Null Sound Device Fehler: {e}")

            logger.info("PJSIP Endpoint gestartet")

            self._register_account()

            # Event Loop
            while self._running:
                self._endpoint.libHandleEvents(10)
                self._process_commands()

        except Exception as e:
            logger.error(f"PJSIP Fehler: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _configure_codecs(self):
        """Audio Codecs priorisieren."""
        try:
            try:
                self._endpoint.codecSetPriority("opus/48000", 255)
            except Exception:
                pass
            self._endpoint.codecSetPriority("G722/16000", 250)
            self._endpoint.codecSetPriority("PCMA/8000", 200)
            self._endpoint.codecSetPriority("PCMU/8000", 199)
            logger.info("Codec-Prioritaeten gesetzt: Opus > G.722 > PCMA > PCMU")
        except Exception as e:
            logger.warning(f"Codec-Konfiguration Fehler: {e}")

    def _register_account(self):
        """SIP Account registrieren."""
        acc_cfg = pj.AccountConfig()
        acc_cfg.idUri = f"sip:{self.user}@{self.server}"
        acc_cfg.regConfig.registrarUri = f"sip:{self.server}:{self.port}"
        acc_cfg.regConfig.timeoutSec = 300  # Re-Registration alle 5 Min

        cred = pj.AuthCredInfo("digest", "*", self.user, 0, self.password)
        acc_cfg.sipConfig.authCreds.append(cred)

        # NAT-Traversal Konfiguration
        # Da der Server eine oeffentliche IP hat (kein NAT), setzen wir
        # die oeffentliche IP direkt im SDP (sdpNatRewriteUse)
        acc_cfg.natConfig.sipStunUse = pj.PJSUA_STUN_USE_DEFAULT
        acc_cfg.natConfig.mediaStunUse = pj.PJSUA_STUN_USE_DEFAULT
        acc_cfg.natConfig.contactRewriteUse = 1
        acc_cfg.natConfig.viaRewriteUse = 1
        acc_cfg.natConfig.sdpNatRewriteUse = 1
        acc_cfg.natConfig.iceEnabled = False
        acc_cfg.natConfig.turnEnabled = False

        # Public IP fuer SDP Contact/Via Header
        if self.public_ip:
            acc_cfg.natConfig.contactRewriteMethod = 2  # Always rewrite
            logger.info(f"NAT: Public IP {self.public_ip} fuer SDP Contact/Via")

        # RTP Media Config
        acc_cfg.mediaConfig.transportConfig.port = 4000  # RTP Start-Port
        acc_cfg.mediaConfig.transportConfig.portRange = 100  # 4000-4100
        if self.public_ip:
            acc_cfg.mediaConfig.transportConfig.publicAddress = self.public_ip
            logger.info(f"RTP: Public Address={self.public_ip}, Ports=4000-4100")

        self._account = AccountCallback()
        self._account.on_reg_state = self._on_reg_state
        self._account.on_incoming_call = self._on_incoming_call
        self._account.create(acc_cfg)

        logger.info(f"Account registriert: {self.user}@{self.server}")

    def _on_reg_state(self, is_registered: bool):
        """Registration Callback (im PJSIP Thread)."""
        self._registered = is_registered
        self._emit_event("reg_state", {"registered": is_registered})

    def _on_incoming_call(self, caller_uri: str, call: CallCallback, remote_ip: str = None):
        """Incoming Call Callback (im PJSIP Thread)."""
        self._current_caller = caller_uri
        self._current_remote_ip = remote_ip
        call.on_state_changed = self._on_call_state
        call.on_media_state = self._on_media_state

        try:
            self._audio_port = AudioMediaPort("AIBridge")
            self._audio_port.createPort(settings.SAMPLE_RATE_SIP, 1, 960, 16)
            self._audio_port.set_incoming_callback(self._on_audio_from_caller)
            call.audio_media_port = self._audio_port
            logger.info("AudioMediaPort fuer Call erstellt")
        except Exception as e:
            logger.error(f"AudioMediaPort Erstellung fehlgeschlagen: {e}")

        self._emit_event("incoming_call", {
            "caller_id": caller_uri,
            "remote_ip": remote_ip
        })

    def _on_call_state(self, state: int, state_text: str):
        """Call State Callback (im PJSIP Thread)."""
        if PJSUA2_AVAILABLE:
            if state == pj.PJSIP_INV_STATE_CONFIRMED:
                self._in_call = True
                self._emit_event("call_active", {})
            elif state == pj.PJSIP_INV_STATE_DISCONNECTED:
                self._in_call = False
                self._current_caller = None
                self._audio_port = None
                self._emit_event("call_ended", {"reason": state_text})

    def _on_media_state(self):
        """Media State Callback - Audio ist jetzt aktiv."""
        logger.info("Media State: Audio verbunden")

    def _on_audio_from_caller(self, audio_data: bytes):
        """Audio vom Anrufer empfangen (im PJSIP Thread)."""
        if self._loop and self.on_audio_received:
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait,
                {"type": "audio_received", "data": audio_data}
            )

    def _emit_event(self, event_type: str, data: dict):
        """Event an asyncio Queue senden (thread-safe)."""
        if self._loop and self._event_queue:
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait,
                {"type": event_type, **data}
            )

    async def _process_events(self):
        """Verarbeitet Events aus dem PJSIP Thread."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.5)
                event_type = event.get("type")

                if event_type == "incoming_call":
                    if self.on_incoming_call:
                        await self.on_incoming_call(
                            event.get("caller_id"), event.get("remote_ip")
                        )
                elif event_type == "call_ended":
                    if self.on_call_ended:
                        await self.on_call_ended(event.get("reason"))
                elif event_type == "audio_received":
                    if self.on_audio_received:
                        await self.on_audio_received(event.get("data"))

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.debug(f"Event processing: {e}")

    def _process_commands(self):
        """Verarbeitet Commands aus der Queue (im PJSIP Thread)."""
        try:
            while True:
                cmd = self._command_queue.get_nowait()
                cmd_type = cmd.get("type")

                if cmd_type == "accept":
                    self._do_accept_call()
                elif cmd_type == "hangup":
                    self._do_hangup()
                elif cmd_type == "reject":
                    self._do_reject_call(cmd.get("status_code", 403))

        except queue.Empty:
            pass

    def _do_accept_call(self):
        """Anruf annehmen (im PJSIP Thread)."""
        if self._account and self._account.current_call:
            prm = pj.CallOpParam()
            prm.statusCode = 200
            self._account.current_call.answer(prm)
            logger.info("Anruf angenommen")

    def _do_reject_call(self, status_code: int = 403):
        """Anruf ablehnen (im PJSIP Thread)."""
        if self._account and self._account.current_call:
            prm = pj.CallOpParam()
            prm.statusCode = status_code
            self._account.current_call.hangup(prm)
            self._account.current_call = None
            logger.info(f"Anruf abgelehnt mit Status {status_code}")

    def _do_hangup(self):
        """Anruf beenden (im PJSIP Thread)."""
        if self._account and self._account.current_call:
            prm = pj.CallOpParam()
            self._account.current_call.hangup(prm)
            logger.info("Anruf beendet")

    async def accept_call(self):
        """Anruf annehmen (thread-safe)."""
        self._command_queue.put({"type": "accept"})

    async def reject_call(self, status_code: int = 403):
        """Anruf ablehnen (thread-safe)."""
        self._command_queue.put({"type": "reject", "status_code": status_code})

    async def hangup(self):
        """Anruf beenden (thread-safe)."""
        self._command_queue.put({"type": "hangup"})

    async def send_audio(self, audio_data: bytes):
        """Audio an Anrufer senden (von AI)."""
        if self._audio_port and self._in_call:
            self._audio_port.queue_audio(audio_data)

    def clear_audio_queue(self) -> int:
        """Leert die Audio-Queue (fuer Barge-In/Interruption)."""
        if self._audio_port:
            return self._audio_port.clear_queue()
        return 0

    async def stop(self):
        """SIP Client stoppen."""
        self._running = False
        if self._pjsip_thread:
            self._pjsip_thread.join(timeout=5)

    def _cleanup(self):
        """PJSIP Ressourcen freigeben."""
        try:
            if self._account:
                self._account.shutdown()
            if self._endpoint:
                self._endpoint.libDestroy()
            logger.info("PJSIP cleanup abgeschlossen")
        except Exception as e:
            logger.debug(f"Cleanup: {e}")
