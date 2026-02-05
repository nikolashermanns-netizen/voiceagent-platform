"""
WebSocket Client fuer Qt GUI.

Verbindet sich mit dem FastAPI Server und empfaengt Live-Updates.
Laeuft in einem separaten Thread um die GUI nicht zu blockieren.
"""

import json
import logging
import time
from typing import Optional

from PySide6.QtCore import QThread, Signal, QTimer

logger = logging.getLogger(__name__)


class WebSocketClient(QThread):
    """
    WebSocket Client Thread fuer die GUI.

    Sendet und empfaengt JSON-Nachrichten vom Server.
    Reconnected automatisch bei Verbindungsverlust.
    """

    connected = Signal()
    disconnected = Signal()
    message_received = Signal(dict)

    def __init__(self, url: str = "ws://localhost:8085/ws"):
        super().__init__()
        self._url = url
        self._running = False
        self._ws = None
        self._send_queue = []

    def run(self):
        """Thread-Main: Verbindet und empfaengt Nachrichten."""
        import websocket
        self._running = True

        while self._running:
            try:
                logger.info(f"Verbinde zu {self._url}...")

                self._ws = websocket.WebSocket()
                self._ws.connect(self._url, timeout=5)
                self.connected.emit()
                logger.info("WebSocket verbunden")

                # Wartende Nachrichten senden
                while self._send_queue:
                    msg = self._send_queue.pop(0)
                    try:
                        self._ws.send(json.dumps(msg))
                    except Exception:
                        pass

                # Empfangsloop
                while self._running:
                    try:
                        self._ws.settimeout(0.5)
                        data = self._ws.recv()
                        if data:
                            msg = json.loads(data)
                            self.message_received.emit(msg)
                    except websocket.WebSocketTimeoutException:
                        # Wartende Nachrichten senden
                        while self._send_queue:
                            msg = self._send_queue.pop(0)
                            try:
                                self._ws.send(json.dumps(msg))
                            except Exception:
                                break
                    except websocket.WebSocketConnectionClosedException:
                        break
                    except Exception as e:
                        logger.debug(f"Receive: {e}")
                        break

            except Exception as e:
                logger.warning(f"WebSocket Fehler: {e}")

            finally:
                if self._ws:
                    try:
                        self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

                self.disconnected.emit()

                # Reconnect nach 3 Sekunden
                if self._running:
                    logger.info("Reconnect in 3 Sekunden...")
                    time.sleep(3)

    def send(self, message: dict):
        """
        Sendet eine Nachricht an den Server.
        Thread-safe: Kann aus dem GUI-Thread aufgerufen werden.
        """
        self._send_queue.append(message)

    def stop(self):
        """Stoppt den Client."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self.wait(timeout=5000)
