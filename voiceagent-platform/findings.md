# Findings & Lessons Learned - Bestell Bot Voice POC

## Audio-Probleme

### 1. Sample-Rate Mismatch (viel Zeit verloren)
**Problem:** Audio war extrem schnell und unverständlich.
**Ursache:** OpenAI Realtime API sendet Audio mit **24kHz**, wir haben es mit 16kHz abgespielt.
**Lösung:** Output-Stream auf 24kHz setzen, Input kann bei 16kHz bleiben (wird vor dem Senden resampled).

```python
# FALSCH: Gleiche Sample-Rate für Input und Output
self._output_stream = sd.OutputStream(samplerate=16000, ...)

# RICHTIG: 24kHz für Output (API liefert 24kHz)
self._output_stream = sd.OutputStream(samplerate=24000, ...)
```

### 2. Audio-Chunk-Größen variabel
**Problem:** API sendet variable Chunk-Größen, Output-Stream erwartet feste Größen.
**Lösung:** Internen Buffer verwenden, der Chunks sammelt und passend ausgibt.

```python
# Chunks sammeln bis genug für einen Frame
self._output_audio_buffer: list[np.ndarray] = []
```

### 3. Gerätauswahl nicht übernommen
**Problem:** LocalAudioDevice nutzte Standard-Gerät statt ausgewähltem.
**Lösung:** Device-IDs explizit an `sd.InputStream/OutputStream` übergeben.

---

## OpenAI Realtime API

### 4. Response muss explizit getriggert werden
**Problem:** Nach Sprach-Ende kam keine AI-Antwort.
**Ursache:** Server-VAD erkennt Sprach-Ende, aber Response wird nicht automatisch generiert.
**Lösung:** NICHT manuell `response.create` senden - die Server-VAD macht das automatisch.

**ABER:** Wenn man `response.create` manuell sendet während bereits eine Response läuft:
```
Error: Conversation already has an active response in progress
```

**Best Practice:** `response_in_progress` Flag tracken, nur senden wenn False.

### 5. Function Calling benötigt spezielle Event-Behandlung
**Events:**
- `response.function_call_arguments.delta` - Argumente werden gestreamt
- `response.function_call_arguments.done` - Argumente komplett, jetzt ausführen
- Nach Ausführung: `conversation.item.create` mit `function_call_output` + `response.create`

### 6. Audio-Callback muss gesetzt sein
**Problem:** Audio wurde empfangen aber nicht abgespielt.
**Ursache:** `set_audio_callback()` wurde nicht aufgerufen oder zu spät.
**Lösung:** Callback in `AudioHandler.start()` setzen, BEVOR `RealtimeClient.connect()`.

---

## Windows-spezifische Probleme

### 7. Unicode/Emoji-Ausgabe in Terminal
**Problem:** `UnicodeEncodeError` bei Emojis in print-Statements.
**Lösung:** 
```python
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
```

### 8. pjsua2 nicht verfügbar auf Windows
**Problem:** SIP-Library pjsua2 ist ein C-Binding, schwer auf Windows zu installieren.
**Lösung:** Optionale Komponente machen, Fallback auf lokales Mikrofon/Lautsprecher.

---

## Qt/PySide6

### 9. Signal-Namen genau beachten
**Problem:** `AttributeError: 'AppSignals' object has no attribute 'transcript_update'`
**Ursache:** Signal hieß `transcript_updated` (mit 'd').
**Lösung:** Signal-Namen immer aus der Definition kopieren, nicht auswendig schreiben.

### 10. UI-Updates nur über Signals
**Problem:** Crashes bei direkten UI-Updates aus anderen Threads.
**Lösung:** Immer Qt Signals verwenden, die automatisch Thread-safe sind.

---

## Katalog/Suche

### 11. Umlaute in Suche
**Problem:** Suche nach "T-Stück" findet "T-Stueck" nicht.
**Lösung:** Normalisierung beider Seiten:
```python
def _normalize_search(text: str) -> str:
    replacements = {"ü": "ue", "ö": "oe", "ä": "ae", ...}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text
```

### 12. Kontext-Größe bei vielen Produkten
**Problem:** 375 Produkte = ~20.000 Zeichen im Kontext, teuer und langsam.
**Lösung:** Function Calling nutzen - nur Produkttypen im Kontext, Details on-demand abfragen.

---

## Architektur-Erkenntnisse

### 13. Audio-Flow muss klar sein
```
Mikrofon (16kHz) 
    → AudioBuffer (in) 
    → AudioHandler (resample zu 24kHz) 
    → RealtimeClient 
    → API

API (24kHz) 
    → RealtimeClient 
    → AudioHandler (Callback) 
    → AudioBuffer (out) 
    → Lautsprecher (24kHz)
```

### 14. Session-State zurücksetzen
**Problem:** Bei neuem Anruf war `response_in_progress` noch True vom letzten Anruf.
**Lösung:** `session.reset()` beim Disconnect aufrufen.

### 15. Graceful Shutdown wichtig
Audio-Streams müssen sauber gestoppt werden, sonst Crashes:
```python
def stop(self):
    self._running = False
    if self._input_stream:
        self._input_stream.stop()
        self._input_stream.close()
```

---

## Performance-Tipps

1. **Audio-Buffer klein halten** (15 Frames = ~300ms) für niedrige Latenz
2. **Non-blocking pulls** im Audio-Callback: `timeout=0`
3. **Logging sparsam** im Audio-Hot-Path (nur alle N Frames)
4. **Resampling ist teuer** - wenn möglich Sample-Raten matchen

---

---

## SIP/VoIP-Integration (viel Zeit verloren!)

### 16. PJSIP/pjsua2 auf Windows extrem schwierig
**Problem:** pjsua2 ist ein C++ Binding, braucht:
- Visual Studio C++ Build Tools
- SWIG installiert und im PATH
- Admin-Rechte für bestimmte Schritte
- Manuelle Compilation mit spezifischen Flags

**Lösung:** **pyVoIP** verwenden - pure Python, `pip install pyVoIP` funktioniert sofort.

```python
# Statt pjsua2:
from pyVoIP.VoIPPhone import VoIPPhone

phone = VoIPPhone(
    server=sip_server,
    port=5060,
    username=sip_user,
    password=sip_password,
    callCallback=self._on_incoming_call
)
phone.start()
```

### 17. Python 3.13: audioop Modul entfernt
**Problem:** `ModuleNotFoundError: No module named 'audioop'` - pyVoIP braucht audioop.
**Ursache:** Python 3.13 hat das `audioop` Modul entfernt (deprecated seit 3.11).
**Lösung:** Backport installieren:
```bash
pip install audioop-lts
```

### 18. pyVoIP Callback-Modell verstehen (KRITISCH!)
**Problem:** Auto-Accept funktionierte nicht, App crashte bei Anrufannahme.
**Ursache:** pyVoIP's `callCallback` läuft in einem eigenen Thread. Der Call MUSS direkt im Callback beantwortet werden!

**FALSCH:**
```python
def _on_incoming_call(self, call):
    self.incoming_call.emit(caller_id)  # Emit signal
    # Später in anderem Thread: call.answer() → CRASH!
```

**RICHTIG:**
```python
def _on_incoming_call(self, call):
    self.incoming_call.emit(caller_id)
    if self._auto_accept:
        time.sleep(0.5)  # Kurz warten für Stabilität
        call.answer()    # DIREKT hier im Callback!
        self._handle_call_audio(call)  # Audio-Loop hier starten
```

### 19. pyVoIP Audio-Format (KRITISCH - viel Zeit verloren!)
**Problem:** Audio war extrem verzerrt und schnell.

**Falsche Annahmen die wir gemacht haben:**
1. ❌ pyVoIP liefert G.711 u-law → FALSCH
2. ❌ pyVoIP liefert 16-bit PCM → FALSCH

**Tatsächliches Format (durch Analyse ermittelt):**
- pyVoIP `read_audio()` liefert **8-bit unsigned PCM** @ 8kHz
- Wertebereich: 0-255
- Stille: 128 (Mittelwert)
- pyVoIP `write_audio()` erwartet ebenfalls 8-bit unsigned PCM

**Korrekte Konvertierung:**
```python
def _upsample_8k_to_16k(self, data: bytes) -> bytes:
    """Konvertiert 8kHz 8-bit unsigned PCM zu 16kHz 16-bit signed PCM."""
    # Interpretiere als 8-bit unsigned
    samples_8bit = np.frombuffer(data, dtype=np.uint8)
    
    # Konvertiere 8-bit unsigned (0-255, center 128) zu 16-bit signed
    samples_16bit = (samples_8bit.astype(np.int16) - 128) * 256
    
    # Upsample 8kHz -> 16kHz mit linearer Interpolation
    new_length = len(samples_16bit) * 2
    indices = np.linspace(0, len(samples_16bit) - 1, new_length)
    upsampled = np.interp(indices, np.arange(len(samples_16bit)), samples_16bit)
    
    return upsampled.astype(np.int16).tobytes()
```

**Wie wir das Format ermittelt haben:**
```powershell
# Audio-Datei analysieren
$bytes = [System.IO.File]::ReadAllBytes("recordings/sip_audio_raw.pcm")
# Min: 0, Max: 149, Stille bei 128 → 8-bit unsigned PCM
```

### 19b. Audio Output (AI → Caller) Konvertierung
**Problem:** AI-Antworten waren verzerrt für den Anrufer.
**Ursache:** 
1. AI sendet **24kHz** 16-bit PCM
2. pyVoIP erwartet **8kHz** 8-bit (PCM oder u-law)

**Lösung:** Korrekte Downsampling-Kette:
```python
def _convert_24k_to_8k(self, data: bytes) -> bytes:
    # 16-bit samples lesen
    samples = np.frombuffer(data, dtype=np.int16)
    
    # Downsample 24kHz -> 8kHz (Faktor 3) mit Interpolation
    target_len = len(samples) // 3
    indices = np.linspace(0, len(samples) - 1, target_len)
    downsampled = np.interp(indices, np.arange(len(samples)), samples)
    
    # Konvertiere zu 8-bit oder u-law je nach Codec
    return self._encode_output(downsampled.astype(np.int16))
```

**Wichtig:** Der richtige Output-Codec muss getestet werden:
- `pcm8`: 8-bit unsigned PCM (Wert 128 = Stille)
- `ulaw`: G.711 μ-law (Wert 0xFF = Stille)
- `alaw`: G.711 A-law

### 20. Codec-Parameter bei AudioBridge
**Problem:** Audio im AudioBridge war beschädigt.
**Ursache:** SIP Client konvertierte bereits zu PCM16, aber AudioBridge versuchte nochmal PCMU zu dekodieren.

**FALSCH:**
```python
# In Controller:
self._audio_bridge.receive_from_sip(pcm_data, codec="PCMU")  # NEIN!
```

**RICHTIG:**
```python
# Wenn SIP Client bereits zu PCM16 konvertiert hat:
self._audio_bridge.receive_from_sip(pcm_data, codec="L16")  # Linear PCM
```

### 20b. NAT/RTP Keepalive Problem
**Problem:** RTP-Daten kommen nur am Anfang, dann stoppt der Stream.
**Ursache:** NAT-Eintrag expired weil keine Pakete zurückgesendet werden.

**Lösung:** Kontinuierlich Audio (auch Stille) an den Server senden:
```python
# Im Audio-Loop: Stille senden um NAT aktiv zu halten
silence = b'\x80' * 160  # 8-bit unsigned PCM Stille
call.write_audio(silence)
```

**Außerdem wichtig:** Lokale IP explizit setzen statt 0.0.0.0:
```python
def _get_local_ip(self) -> str:
    """Ermittelt die lokale IP für RTP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((sip_server, 80))  # Verbinde zu SIP Server
    local_ip = s.getsockname()[0]
    s.close()
    return local_ip

# Bei VoIPPhone:
phone = VoIPPhone(..., myIP=local_ip, ...)
```

### 21. Sipgate-spezifische Konfiguration
```env
SIP_SERVER=sipconnect.sipgate.de
SIP_USERNAME=<deine sipgate web user-id>  # z.B. 1234567t0
SIP_PASSWORD=<dein sipgate web passwort>
SIP_PORT=5060
```

**Wichtig:** Sipgate versucht Opus-Codec, pyVoIP unterstützt nur PCMU/PCMA:
```
UserWarning: RTP Payload type opus not found.
```
→ Kann ignoriert werden, Fallback auf PCMU funktioniert.

---

## Allgemeine Python/Windows Probleme

### 22. Circular Imports vermeiden
**Problem:** `ImportError: cannot import name 'SIPClient' from partially initialized module`
**Ursache:** `__init__.py` Dateien importieren Module, die sich gegenseitig importieren.

**Lösung:** Keine Klassen in `__init__.py` importieren:
```python
# FALSCH in core/__init__.py:
from .controller import CallController  # Kann Circular Import verursachen

# RICHTIG:
# Leer lassen oder nur __all__ definieren
```

Stattdessen direkt importieren wo gebraucht:
```python
from core.controller import CallController
```

### 23. Port-Konflikte bei Neustart
**Problem:** `[WinError 10048] Socketadresse bereits verwendet`
**Ursache:** Alte Python-Prozesse laufen noch im Hintergrund.

**Lösung vor jedem Start:**
```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
python main.py
```

### 24. PowerShell Syntax-Unterschiede
**Problem:** Bash-Befehle funktionieren nicht in PowerShell.
- `&&` → `;` (oder separate Befehle)
- Heredoc `<<'EOF'` → nicht verfügbar, einfache Strings nutzen
- `export VAR=value` → `$env:VAR = "value"`

---

## Checkliste für Produktion

- [ ] Sample-Raten konsistent (Input 16kHz, Output 24kHz für OpenAI)
- [ ] Audio-Callbacks vor connect() setzen
- [ ] Session-State bei Disconnect zurücksetzen
- [ ] `response_in_progress` Flag tracken
- [ ] Unicode-Encoding für Windows
- [ ] Graceful Shutdown für alle Streams
- [ ] Umlaute in Suche normalisieren
- [ ] Function Calling für große Datensätze
- [ ] **pyVoIP statt pjsua2 für Windows-Kompatibilität**
- [ ] **audioop-lts für Python 3.13+**
- [ ] **G.711 u-law korrekt dekodieren (nicht als raw PCM behandeln!)**
- [ ] **call.answer() DIREKT im pyVoIP Callback**
- [ ] **Codec-Parameter "L16" wenn Audio bereits konvertiert**
- [ ] **Alte Python-Prozesse vor Neustart beenden**

---

## SDP/Codec-Analyse (2026-02-04)

### 25. SDP-Codec aus pyVoIP auslesen

**Problem:** Welcher Codec wird für die Telefonverbindung verwendet?

**Lösung:** Die SDP-Information ist in pyVoIP verfügbar:

```python
# Nach call.answer():
for rtp in call.RTPClients:
    # Zeigt den bevorzugten Codec
    print(f"Preference: {rtp.preference}")  # z.B. <PayloadType.PCMA: 8>
    print(f"Assoc: {rtp.assoc}")  # Alle verfügbaren Codecs

# Oder aus dem SIP Request Body:
if hasattr(call, 'request') and call.request:
    sdp = call.request.body
    # sdp['m'][0]['attributes'] enthält rtpmap mit Codec-Details
```

### 26. Sipgate verwendet A-law (PCMA), nicht PCM!

**Wichtige Erkenntnis aus SDP-Logs:**

```
'preference': <PayloadType.PCMA: 8>
'assoc': {8: <PayloadType.PCMA: 8>, 0: <PayloadType.PCMU: 0>, ...}

SDP rtpmap:
'8': {'name': 'PCMA', 'frequency': '8000'}
'0': {'name': 'PCMU', 'frequency': '8000'}
```

**Bedeutung:**
- pyVoIP wählt **A-law (G.711 PCMA)** als bevorzugten Codec
- Sample Rate ist **8000 Hz** (8kHz)
- pyVoIP dekodiert eingehend A-law → 8-bit unsigned PCM
- **Ausgehend müssen wir A-law encodieren, nicht raw PCM!**

**Korrekte Output-Konvertierung:**

```python
def _convert_ai_to_sip(self, data: bytes) -> bytes:
    """Konvertiert 24kHz 16-bit AI Audio zu 8kHz A-law für SIP."""
    samples = np.frombuffer(data, dtype=np.int16)
    
    # Resample 24kHz → 8kHz
    ratio = 24000 / 8000  # = 3
    target_len = int(len(samples) / ratio)
    indices = np.linspace(0, len(samples) - 1, target_len)
    samples_8k = np.interp(indices, np.arange(len(samples)), samples).astype(np.int16)
    
    # Encode zu A-law
    return self._encode_alaw(samples_8k)

def _encode_alaw(self, samples: np.ndarray) -> bytes:
    """G.711 A-law Encoding."""
    result = []
    for s in samples:
        s = max(-32768, min(32767, int(s)))
        sign = 0x00 if s >= 0 else 0x80
        s = abs(s)
        
        if s < 256:
            exp, mant = 0, s >> 4
        elif s < 512:
            exp, mant = 1, (s >> 5) & 0x0F
        # ... (vollständige Tabelle im Code)
        
        result.append((sign | (exp << 4) | mant) ^ 0x55)
    return bytes(result)
```

### 27. OpenAI Realtime API Audio-Format

**Input (zum AI):** 16kHz, 16-bit signed PCM, mono
**Output (vom AI):** 24kHz, 16-bit signed PCM, mono

**Konvertierungskette:**
```
Telefon (8kHz A-law) 
  → pyVoIP dekodiert → 8kHz 8-bit unsigned PCM
  → Upsample + Convert → 16kHz 16-bit signed PCM 
  → OpenAI API

OpenAI API → 24kHz 16-bit signed PCM
  → Downsample → 8kHz 16-bit signed PCM
  → A-law encode → 8kHz A-law
  → pyVoIP → Telefon
```

### 28. Frame-Größe für pyVoIP

**KRITISCH:** pyVoIP erwartet exakt **160-byte Frames** (20ms @ 8kHz, 8-bit).

Die AI sendet größere Blöcke (z.B. 2400 samples @ 24kHz = 100ms).
Nach Konvertierung zu 8kHz 8-bit: 800 bytes pro Block.

**Lösung:** AI-Audio in 160-byte Chunks aufteilen:

```python
FRAME_SIZE = 160  # 20ms @ 8kHz, 8-bit

for i in range(0, len(converted), FRAME_SIZE):
    chunk = converted[i:i + FRAME_SIZE]
    if len(chunk) < FRAME_SIZE:
        chunk = chunk + b'\x80' * (FRAME_SIZE - len(chunk))  # Padding mit Stille
    call.write_audio(chunk)
```

### 29. pyVoIP Opus Codec

**pyVoIP unterstützt KEIN Opus** - nur PCMA und PCMU (G.711).

Logs zeigen: "RTP Payload type opus not found"

### 30. Audioop für zuverlässige Konvertierung

Python's `audioop` Modul (oder `audioop-lts` für Python 3.13+) ist zuverlässiger als manuelle Konvertierung:

```python
import audioop

# Resample 24kHz → 8kHz
resampled, _ = audioop.ratecv(data, 2, 1, 24000, 8000, None)

# 16-bit signed → 8-bit unsigned
pcm_8bit = audioop.lin2lin(resampled, 2, 1)
```

**Wichtig:** `audioop.lin2lin` mit width 1 gibt 8-bit **unsigned** PCM zurück - genau was pyVoIP erwartet!

---

## PJSIP auf Linux Server (2026-02-04)

### 31. pyVoIP Audioqualität unzureichend → PJSIP

**Problem:** pyVoIP lieferte nur 8kHz G.711, sehr schlechte Audioqualität.

**Lösung:** PJSIP auf Linux Server verwenden:
- Unterstützt Opus @ 48kHz (deutlich besser als G.711 @ 8kHz)
- Professionelle RTP-Timing
- Bessere Codec-Unterstützung

**Architektur:**
```
Telefon → Sipgate → Linux Server (PJSIP + FastAPI)
                        ↓ WebSocket
                    OpenAI Realtime API
                        ↓ WebSocket
                    Lokale Python GUI (PySide6)
```

### 32. Docker network_mode: host für SIP

**Problem:** SIP-Registration schlug fehl mit NAT-Problemen.

**Lösung:** `network_mode: host` in docker-compose.yml:
```yaml
services:
  bestell-bot:
    network_mode: host  # WICHTIG für SIP!
    privileged: true
    cap_add:
      - NET_ADMIN
      - NET_RAW
```

**Warum:** SIP braucht direkte Netzwerk-Kontrolle für RTP-Ports.

### 33. PJSIP Null Sound Device

**Problem:** `Error opening sound device: Unable to find default audio device`

**Ursache:** Docker Container hat keine Audio-Hardware.

**Lösung:** Null Sound Device aktivieren:
```python
self._endpoint.audDevManager().setNullDev()
```

### 34. PJSIP Threading-Modell (KRITISCH!)

**Problem:** `Assertion failed: "Calling pjlib from unknown/external thread"`

**Ursache:** PJSIP muss in einem dedizierten Thread laufen.

**Lösung:** Separater Thread für PJSIP mit asyncio Queue für Events:
```python
self._pjsip_thread = threading.Thread(target=self._run_pjsip, daemon=True)
self._pjsip_thread.start()

# Thread-safe Events via asyncio Queue
self._loop.call_soon_threadsafe(
    self._event_queue.put_nowait,
    {"type": "audio_received", "data": audio_data}
)
```

### 35. PJSIP ByteVector für Audio-Frames

**Problem:** `onFrameRequested Error: in method 'MediaFrame_buf_set', argument 2 of type 'pj::ByteVector *'`

**Ursache:** PJSIP Python bindings erwarten `pj.ByteVector`, nicht `bytes`.

**FALSCH:**
```python
frame.buf = audio_data  # bytes → ERROR!
```

**RICHTIG:**
```python
frame.buf = pj.ByteVector(list(audio_data))  # Schnelle Konvertierung
```

### 36. Audio-Frame-Splitting (KRITISCH!)

**Problem:** AI Audio kam nur in kurzen Fetzen an, dann Stille.

**Ursache:** OpenAI sendet variable Chunk-Größen, aber PJSIP erwartet exakt 20ms Frames.

**Lösung:** Audio in 1920-byte Frames aufteilen (960 samples @ 48kHz, 16-bit):
```python
def queue_audio(self, audio_data: bytes):
    frame_size = self._samples_per_frame * 2  # 1920 bytes
    
    self._audio_buffer += audio_data
    
    while len(self._audio_buffer) >= frame_size:
        frame = self._audio_buffer[:frame_size]
        self._audio_buffer = self._audio_buffer[frame_size:]
        self._outgoing_queue.append(frame)
```

### 37. Audio Queue-Größe (KRITISCH!)

**Problem:** Audio hatte Lücken, dann wurde es schnell abgespielt.

**Ursache:** `deque(maxlen=100)` war zu klein - bei 20ms Frames nur 2 Sekunden!

**Symptom in Logs:**
```
[TX] Frames: 700, Audio: 301, Queue: 28  ← Queue fast voll
[TX] Frames: 800, Audio: 329, Queue: 0   ← Queue leer, ältere Frames überschrieben!
```

**Lösung:** Queue auf 500 Frames erhöhen (10 Sekunden):
```python
self._outgoing_queue: deque = deque(maxlen=500)
```

### 38. Audio-Resampling Pipeline

**Konvertierungskette für PJSIP mit Opus @ 48kHz:**
```
Telefon (48kHz Opus) 
  → PJSIP dekodiert → 48kHz 16-bit PCM
  → Resample → 16kHz 16-bit PCM 
  → OpenAI Realtime API (erwartet 16kHz)

OpenAI API → 24kHz 16-bit PCM
  → Resample → 48kHz 16-bit PCM
  → PJSIP enkodiert → 48kHz Opus
  → Telefon
```

**Resampling mit scipy:**
```python
from scipy import signal as scipy_signal
import numpy as np

def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    if from_rate == to_rate:
        return audio_data
    
    samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
    num_samples = int(len(samples) * to_rate / from_rate)
    resampled = scipy_signal.resample(samples, num_samples)
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
    
    return resampled.tobytes()
```

### 39. Firewall-Ports für SIP/RTP

**Benötigte Ports:**
- **5060 UDP** - SIP Signaling
- **4000-4100 UDP** - RTP Media (PJSIP Default-Range)
- **8085 TCP** - API für lokale GUI

**iptables Regel:**
```bash
sudo iptables -I INPUT -p udp --dport 5060 -j ACCEPT
sudo iptables -I INPUT -p udp --dport 4000:4100 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 8085 -j ACCEPT
```

### 40. OpenAI Realtime API mit aiohttp

**Problem:** `openai` SDK Realtime API änderte sich, alte Syntax funktioniert nicht mehr.

**Lösung:** Direkte WebSocket-Verbindung mit aiohttp:
```python
import aiohttp

headers = {
    "Authorization": f"Bearer {api_key}",
    "OpenAI-Beta": "realtime=v1"
}

session = aiohttp.ClientSession()
ws = await session.ws_connect(
    "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17",
    headers=headers
)

# Session konfigurieren
await ws.send_str(json.dumps({
    "type": "session.update",
    "session": {
        "modalities": ["text", "audio"],
        "voice": "alloy",
        "input_audio_format": "pcm16",
        "output_audio_format": "pcm16",
        "turn_detection": {"type": "server_vad"}
    }
}))
```

---

## Performance-Optimierungen (PJSIP)

### 41. ByteVector Cache für Stille

**Problem:** Stille-Frame bei jedem Request neu erstellen ist langsam.

**Lösung:** Einmal erstellen und cachen:
```python
if not hasattr(self, '_silence_vector'):
    self._silence_vector = pj.ByteVector([0] * (self._samples_per_frame * 2))
frame.buf = self._silence_vector
```

### 42. Schnelle ByteVector-Konvertierung

**LANGSAM (for-loop):**
```python
bv = pj.ByteVector()
for b in audio_data:
    bv.append(b)  # ~1920 append-Aufrufe pro Frame!
```

**SCHNELL (list constructor):**
```python
frame.buf = pj.ByteVector(list(audio_data))  # Einmaliger Aufruf
```

---

## Checkliste für PJSIP-Server

- [ ] Docker mit `network_mode: host` und `privileged: true`
- [ ] Null Sound Device aktivieren
- [ ] PJSIP in eigenem Thread
- [ ] ByteVector für frame.buf verwenden
- [ ] Audio in 20ms Frames aufteilen
- [ ] Queue mindestens 500 Frames (10 Sekunden)
- [ ] Resampling: 48kHz (PJSIP) ↔ 16kHz/24kHz (OpenAI)
- [ ] Firewall-Ports öffnen (5060, 4000-4100, 8085)
- [ ] aiohttp für OpenAI WebSocket

---

## VoiceAgent Platform Build (2026-02-05)

### 43. response_in_progress Flag (KRITISCH!)

**Problem:** OpenAI Realtime API gibt Error wenn `response.create` gesendet wird während bereits eine Response läuft:
```
Error: Conversation already has an active response in progress
```

**Betroffen:**
- `trigger_greeting()` - kann kollidieren wenn Server-VAD schon eine Response triggert
- `_send_function_result()` - sendet `response.create` nach Function Call Output

**Lösung:** Flag `_response_in_progress` tracken:
```python
# Setzen bei:
self._response_in_progress = True   # response.created Event
self._response_in_progress = False  # response.done Event
self._response_in_progress = False  # speech_started (Interruption)
self._response_in_progress = False  # disconnect()

# Prüfen vor response.create:
if self._response_in_progress:
    # Warten oder überspringen
```

**Wichtig:** Bei `_send_function_result` muss man warten (max 5s Loop) bis die vorherige Response fertig ist, BEVOR man `response.create` sendet. Einfach überspringen geht nicht - die Function-Antwort MUSS generiert werden.

### 44. NAT/Public IP für RTP (KRITISCH!)

**Problem:** Sipgate sendet RTP an die IP aus dem SDP. Wenn dort eine private Docker-IP oder 0.0.0.0 steht, kommt kein Audio an.

**Lösung:** Public IP explizit in PJSIP setzen:
```python
# Transport Config
tp_cfg.publicAddress = "142.132.212.248"  # Server Public IP

# Account Media Config (für RTP)
acc_cfg.mediaConfig.transportConfig.port = 4000       # RTP Start Port
acc_cfg.mediaConfig.transportConfig.portRange = 100    # 4000-4100
acc_cfg.mediaConfig.transportConfig.publicAddress = "142.132.212.248"
```

**Außerdem:** NAT Contact Rewrite aktivieren:
```python
acc_cfg.natConfig.contactRewriteMethod = 2  # Always rewrite mit Public IP
acc_cfg.natConfig.sdpNatRewriteUse = 1      # Public IP im SDP
```

### 45. PJSIP Conference Bridge Clock Rate

**Problem:** Wenn Sipgate keinen Opus-Codec verhandelt sondern auf PCMA (8kHz) zurückfällt, stimmen die Sample-Raten nicht.

**Lösung:** PJSIP's Conference Bridge resampled automatisch. Die Bridge Clock Rate muss auf 48kHz gesetzt sein:
```python
ep_cfg.medConfig.clockRate = 48000  # Bridge arbeitet immer bei 48kHz
```

Damit liefert unsere AudioMediaPort (die auch bei 48kHz arbeitet) immer korrekte Daten, egal welcher Codec tatsächlich verhandelt wird. PJSIP resampled intern.

**Codec-Detection loggen:**
```python
port_info = call_audio.getPortInfo()
logger.info(f"Negotiated: {port_info.format.clockRate}Hz")
```

### 46. Docker Compose v1 vs v2

**Problem:** `docker compose` (v2 Plugin) existiert nicht auf älteren Servern.
```
docker: unknown command: docker compose
```

**Lösung:** Beide Varianten erkennen:
```bash
if docker compose version &> /dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE="docker-compose"
fi
```

### 47. Firewall: Sipgate IP Ranges

**Sipgate Infrastruktur:**
- SIP Signaling: `217.10.68.0/24`
- Media/RTP: `217.10.64.0/20` (deckt 217.10.64.0 - 217.10.79.255)

**Firewall-Regeln (iptables):**
```bash
# SIP: nur Sipgate
iptables -I INPUT -p udp -s 217.10.68.0/24 --dport 5060 -j ACCEPT

# RTP: nur Sipgate Media
iptables -I INPUT -p udp -s 217.10.64.0/20 --dport 4000:4100 -j ACCEPT

# API: nur WireGuard VPN
iptables -I INPUT -p tcp -s 10.200.200.0/24 --dport 8085 -j ACCEPT
```

**WARNUNG:** Offene RTP-Regeln (ohne Source-Restriction) sind ein Sicherheitsrisiko! Alte Regeln immer entfernen:
```bash
iptables -D INPUT -p udp --dport 4000:4100 -j ACCEPT  # Offene Regel löschen
```

### 48. Katalog-Daten Deployment

**Problem:** `docker-compose.yml` hatte Volume-Mount auf `../Bestell Bot Voice/server/system_katalog` - existiert nicht auf dem Server.

**Lösung:** Katalog-Daten liegen im `data/system_katalog/` Verzeichnis (Teil des data/-Mounts):
- Lokal: Manuell aus Bestell Bot Voice kopieren
- Server: Per `scp` hochladen
- Docker: Über `./data:/app/data` Mount verfügbar unter `/app/data/system_katalog`

```bash
# Katalog auf Server kopieren:
scp -r "Bestell Bot Voice/server/system_katalog/"* bot:/opt/voiceagent-platform/voiceagent-platform/data/system_katalog/
```

### 49. Audio Queue Warning Threshold

**Problem:** Queue-Warnung bei 50 Frames war viel zu früh (5% von maxlen=1000). Logs wurden mit Warnungen geflutet.

**Lösung:** Warnung bei 50% (500/1000 Frames):
```python
queue_len = len(self._outgoing_queue)
if queue_len == 500:
    logger.warning(f"[TX] Audio Queue halb voll: {queue_len}/1000 Frames")
```

### 50. Session State Reset bei Disconnect

**Problem:** Nach Anruf-Ende war `response_in_progress` noch True. Beim nächsten Anruf wurde die Begrüßung übersprungen.

**Lösung:** Vollständiger State-Reset in `disconnect()`:
```python
self._audio_chunk_count = 0
self._sent_audio_count = 0
self._response_in_progress = False  # WICHTIG!
```

### 51. STUN Server Redundanz

**Problem:** Wenn `stun.sipgate.de` nicht erreichbar ist, schlägt NAT-Detection fehl.

**Lösung:** Mehrere STUN Server konfigurieren:
```python
ep_cfg.uaConfig.stunServer.append("stun.sipgate.de")
ep_cfg.uaConfig.stunServer.append("stun.l.google.com:19302")
```

### 52. SIP Re-Registration Timeout

**Problem:** Default Re-Registration Interval kann zu lang sein. Bei NAT-Firewalls expired der Binding sonst.

**Lösung:** Explicit auf 300 Sekunden (5 Min) setzen:
```python
acc_cfg.regConfig.timeoutSec = 300
```

### 53. Python 3.12: distutils entfernt → setuptools nötig für PJSIP Build

**Problem:** PJSIP Python Bindings Build (`make` in `pjsip-apps/src/swig/python`) schlägt fehl:
```
ModuleNotFoundError: No module named 'distutils'
```

**Ursache:** Python 3.12 hat das `distutils` Modul komplett entfernt (deprecated seit 3.10).
Das PJSIP Build-System (`setup.py`) verwendet intern `distutils.core.setup()`.

**Lösung:** `pip install setuptools` BEVOR die Python Bindings gebaut werden:
```dockerfile
RUN ... \
    && make dep && make \
    && pip install setuptools \       # ← HIER! VOR dem SWIG/Python-Build
    && cd pjsip-apps/src/swig/python \
    && make \
    && make install
```

`setuptools` enthält einen `distutils`-Compatibility-Shim der das entfernte Modul bereitstellt.

**Generell:** Betrifft jedes Python-Paket das noch `distutils` nutzt. Bei Python 3.12+
immer prüfen ob `setuptools` als Build-Dependency nötig ist.

### 54. SWIG-Dependency für PJSIP Python Bindings (fehlte im Dockerfile)

**Problem:** PJSIP Python Bindings Build schlägt fehl:
```
/bin/sh: 1: swig: not found
make: *** [Makefile:20: pjsua2_wrap.cpp] Error 127
```

**Ursache:** SWIG (Simplified Wrapper and Interface Generator) erzeugt C++ → Python Wrapper.
Ohne SWIG kann `pjsua2_wrap.cpp` nicht aus der Interface-Definition `pjsua2.i` generiert werden.

**Lösung:** `swig` in die apt-get Dependencies aufnehmen:
```dockerfile
RUN apt-get update && apt-get install -y \
    build-essential \
    ...
    swig \              # ← Für Python Bindings!
    wget
```

### 55. PJSIP Build-Reihenfolge im Dockerfile (alle Stolperfallen)

Die PJSIP-Compilation hat eine strikte Reihenfolge. Fehlermeldungen sind oft nicht hilfreich.

**Korrekte Reihenfolge:**
```
1. apt-get: build-essential, libopus-dev, libspeex-dev, swig, pkg-config, ...
2. ./configure --enable-shared --with-opus=/usr --with-speex=/usr
3. make dep              ← Dependencies berechnen (sonst: undefined references)
4. make                  ← C/C++ Libraries kompilieren
5. pip install setuptools  ← Python 3.12+ distutils-Shim
6. cd pjsip-apps/src/swig/python
7. make                  ← SWIG generiert Wrapper + kompiliert _pjsua2.so
8. make install          ← Installiert pjsua2 in site-packages
```

**Häufige Fehler je nach fehlendem Schritt:**

| Fehlt | Symptom |
|-------|---------|
| `swig` | `swig: not found` bei Schritt 7 |
| `make dep` | Undefined references beim Linken |
| `setuptools` | `No module named 'distutils'` bei Schritt 7 |
| `--enable-shared` | `.so` Dateien fehlen, Linking schlägt fehl |
| `libopus-dev` | Opus-Codec nicht verfügbar, nur G.711 |
| `pkg-config` | Configure findet installierte Libs nicht |
| `libspeexdsp-dev` | Speex DSP (Echo Cancellation) fehlt |

### 56. Docker Build-Context bei verschachtelter Projektstruktur

**Problem:** `COPY core/requirements.txt` schlägt fehl.

**Ursache:** Dockerfile liegt in `core/Dockerfile`, aber braucht Zugriff auf `core/` UND `agents/`.

**Lösung in docker-compose.yml:**
```yaml
services:
  voiceagent-core:
    build:
      context: .                    # Root = Build-Context (enthält core/ + agents/)
      dockerfile: core/Dockerfile   # Dockerfile relativ zum Context
```

**FALSCH:**
```yaml
    build:
      context: ./core     # ← Dann ist agents/ nicht erreichbar!
```

---

## Checkliste für VoiceAgent Platform

- [ ] `.env` mit echten Credentials auf Server
- [ ] `SIP_PUBLIC_IP` auf Server Public IP gesetzt
- [ ] Katalog-Daten in `data/system_katalog/` vorhanden
- [ ] Firewall: SIP 5060 nur Sipgate, RTP 4000-4100 nur Sipgate Media
- [ ] Firewall: API 8085 nur WireGuard
- [ ] `response_in_progress` Flag wird korrekt getrackt
- [ ] Conference Bridge Clock Rate auf 48kHz
- [ ] RTP Public Address auf Server IP
- [ ] Docker Compose v1 oder v2 erkannt
- [ ] STUN Server erreichbar
- [ ] `setuptools` vor PJSIP Python Binding Build installiert (Python 3.12+)
- [ ] `swig` in Dockerfile apt-get Dependencies
- [ ] Build-Context in docker-compose.yml auf Root gesetzt (nicht `./core`)
