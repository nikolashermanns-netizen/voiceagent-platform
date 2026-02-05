"""
VoiceAgent Platform - PySide6 GUI Main Window.

Dashboard mit:
- Call-Status und Caller-ID
- Live-Transkript
- Bestelluebersicht
- Agent-Auswahl
- Task-Liste
- Ideen/Projekte
"""

import json
import logging
import sys
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QTabWidget, QGroupBox,
    QListWidget, QListWidgetItem, QComboBox, QSplitter,
    QStatusBar, QFrame, QGridLayout
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread
from PySide6.QtGui import QFont, QColor

from gui.ws_client import WebSocketClient

logger = logging.getLogger(__name__)


class StatusIndicator(QFrame):
    """Farbiger Status-Indikator (gruen/rot/gelb)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setFrameShape(QFrame.Box)
        self.set_status("offline")

    def set_status(self, status: str):
        colors = {
            "online": "#22c55e",
            "offline": "#ef4444",
            "warning": "#eab308",
            "active": "#3b82f6",
        }
        color = colors.get(status, colors["offline"])
        self.setStyleSheet(
            f"background-color: {color}; border-radius: 8px; border: none;"
        )


class MainWindow(QMainWindow):
    """Haupt-Dashboard-Fenster."""

    def __init__(self, api_url: str = "ws://localhost:8085/ws"):
        super().__init__()
        self.setWindowTitle("VoiceAgent Platform")
        self.setMinimumSize(1200, 800)

        self._api_url = api_url
        self._ws_client = WebSocketClient(api_url)

        self._setup_ui()
        self._connect_signals()
        self._apply_styles()

        # WebSocket verbinden
        self._ws_client.start()

    def _setup_ui(self):
        """UI aufbauen."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # === Header ===
        header = self._create_header()
        main_layout.addWidget(header)

        # === Splitter: Links (Transkript) | Rechts (Panels) ===
        splitter = QSplitter(Qt.Horizontal)

        # Linke Seite: Transkript
        left_panel = self._create_transcript_panel()
        splitter.addWidget(left_panel)

        # Rechte Seite: Tabs
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([600, 500])
        main_layout.addWidget(splitter, 1)

        # === Status Bar ===
        self.statusBar().showMessage("Verbinde...")

    def _create_header(self) -> QWidget:
        """Header mit Status und Controls."""
        header = QGroupBox()
        layout = QHBoxLayout(header)

        # SIP Status
        sip_group = QHBoxLayout()
        self._sip_indicator = StatusIndicator()
        self._sip_label = QLabel("SIP: Offline")
        self._sip_label.setFont(QFont("Segoe UI", 10))
        sip_group.addWidget(self._sip_indicator)
        sip_group.addWidget(self._sip_label)
        layout.addLayout(sip_group)

        # Call Status
        call_group = QHBoxLayout()
        self._call_indicator = StatusIndicator()
        self._call_label = QLabel("Kein Anruf")
        self._call_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        call_group.addWidget(self._call_indicator)
        call_group.addWidget(self._call_label)
        layout.addLayout(call_group)

        # Agent Status
        agent_group = QHBoxLayout()
        agent_label = QLabel("Agent:")
        self._agent_combo = QComboBox()
        self._agent_combo.setMinimumWidth(180)
        agent_group.addWidget(agent_label)
        agent_group.addWidget(self._agent_combo)
        layout.addLayout(agent_group)

        layout.addStretch()

        # Buttons
        self._btn_hangup = QPushButton("Auflegen")
        self._btn_hangup.setEnabled(False)
        self._btn_hangup.setStyleSheet(
            "QPushButton { background-color: #ef4444; color: white; "
            "padding: 8px 16px; border-radius: 4px; }"
        )
        layout.addWidget(self._btn_hangup)

        self._btn_mute = QPushButton("Stumm")
        self._btn_mute.setCheckable(True)
        layout.addWidget(self._btn_mute)

        return header

    def _create_transcript_panel(self) -> QWidget:
        """Transkript-Panel (links)."""
        panel = QGroupBox("Live-Transkript")
        layout = QVBoxLayout(panel)

        self._transcript = QTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setFont(QFont("Consolas", 10))
        layout.addWidget(self._transcript)

        return panel

    def _create_right_panel(self) -> QWidget:
        """Rechtes Panel mit Tabs."""
        tabs = QTabWidget()

        # Tab 1: Bestellung
        tabs.addTab(self._create_order_tab(), "Bestellung")

        # Tab 2: Tasks
        tabs.addTab(self._create_tasks_tab(), "Tasks")

        # Tab 3: Ideen
        tabs.addTab(self._create_ideas_tab(), "Ideen")

        # Tab 4: Agenten
        tabs.addTab(self._create_agents_tab(), "Agenten")

        # Tab 5: Debug
        tabs.addTab(self._create_debug_tab(), "Debug")

        return tabs

    def _create_order_tab(self) -> QWidget:
        """Bestellungs-Tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._order_list = QListWidget()
        self._order_list.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self._order_list)

        # Zusammenfassung
        self._order_summary = QLabel("Bestellung: 0 Positionen")
        self._order_summary.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(self._order_summary)

        return widget

    def _create_tasks_tab(self) -> QWidget:
        """Tasks-Tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._task_list = QListWidget()
        self._task_list.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self._task_list)

        return widget

    def _create_ideas_tab(self) -> QWidget:
        """Ideen-Tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._ideas_list = QListWidget()
        self._ideas_list.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self._ideas_list)

        return widget

    def _create_agents_tab(self) -> QWidget:
        """Agenten-Tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info_label = QLabel("Verfuegbare Agenten:")
        info_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(info_label)

        self._agents_list = QListWidget()
        self._agents_list.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self._agents_list)

        # Firewall
        fw_group = QGroupBox("SIP Firewall")
        fw_layout = QHBoxLayout(fw_group)
        self._fw_label = QLabel("Status: Unbekannt")
        self._btn_fw_toggle = QPushButton("Toggle")
        fw_layout.addWidget(self._fw_label)
        fw_layout.addWidget(self._btn_fw_toggle)
        layout.addWidget(fw_group)

        return widget

    def _create_debug_tab(self) -> QWidget:
        """Debug-Tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._debug_log = QTextEdit()
        self._debug_log.setReadOnly(True)
        self._debug_log.setFont(QFont("Consolas", 9))
        layout.addWidget(self._debug_log)

        btn_clear = QPushButton("Log leeren")
        btn_clear.clicked.connect(self._debug_log.clear)
        layout.addWidget(btn_clear)

        return widget

    def _connect_signals(self):
        """Verbindet WebSocket Signals mit Slots."""
        self._ws_client.connected.connect(self._on_ws_connected)
        self._ws_client.disconnected.connect(self._on_ws_disconnected)
        self._ws_client.message_received.connect(self._on_ws_message)

        self._btn_hangup.clicked.connect(self._on_hangup)
        self._btn_mute.toggled.connect(self._on_mute_toggle)
        self._agent_combo.currentTextChanged.connect(self._on_agent_changed)

    def _apply_styles(self):
        """Wendet das Stylesheet an."""
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QGroupBox {
                background-color: #2a2a3e;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 10px;
                margin-top: 5px;
                color: #cdd6f4;
            }
            QGroupBox::title { color: #89b4fa; }
            QLabel { color: #cdd6f4; }
            QTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
                padding: 6px;
            }
            QListWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
            }
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background-color: #3a3a4e; }
            QPushButton {
                background-color: #3a3a4e;
                color: #cdd6f4;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #4a4a5e; }
            QPushButton:pressed { background-color: #2a2a3e; }
            QComboBox {
                background-color: #3a3a4e;
                color: #cdd6f4;
                border: 1px solid #4a4a5e;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QTabWidget::pane {
                background-color: #2a2a3e;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #2a2a3e;
                color: #cdd6f4;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { background-color: #3a3a4e; color: #89b4fa; }
            QStatusBar { background-color: #1e1e2e; color: #6c7086; }
            QSplitter::handle { background-color: #3a3a4e; }
        """)

    # ============== WebSocket Handlers ==============

    @Slot()
    def _on_ws_connected(self):
        self.statusBar().showMessage("Verbunden mit Server")
        self._sip_label.setText("SIP: Verbinde...")

    @Slot()
    def _on_ws_disconnected(self):
        self.statusBar().showMessage("Verbindung verloren - Reconnecting...")
        self._sip_indicator.set_status("offline")
        self._sip_label.setText("SIP: Offline")

    @Slot(dict)
    def _on_ws_message(self, data: dict):
        """Verarbeitet eingehende WebSocket-Nachrichten."""
        msg_type = data.get("type", "")

        if msg_type == "status":
            self._handle_status(data)
        elif msg_type == "call_incoming":
            self._handle_call_incoming(data)
        elif msg_type == "call_active":
            self._handle_call_active(data)
        elif msg_type == "call_ended":
            self._handle_call_ended(data)
        elif msg_type == "transcript":
            self._handle_transcript(data)
        elif msg_type == "order_update":
            self._handle_order_update(data)
        elif msg_type == "function_call":
            self._handle_function_call(data)
        elif msg_type == "function_result":
            self._handle_function_result(data)
        elif msg_type == "agent_changed":
            self._handle_agent_changed(data)
        elif msg_type == "firewall_status":
            self._handle_firewall_status(data)
        elif msg_type == "debug_event":
            self._handle_debug_event(data)

    def _handle_status(self, data: dict):
        sip_registered = data.get("sip_registered", False)
        call_active = data.get("call_active", False)

        if sip_registered:
            self._sip_indicator.set_status("online")
            self._sip_label.setText("SIP: Registriert")
        else:
            self._sip_indicator.set_status("offline")
            self._sip_label.setText("SIP: Offline")

        if call_active:
            self._call_indicator.set_status("active")
            self._btn_hangup.setEnabled(True)
        else:
            self._call_indicator.set_status("offline")
            self._call_label.setText("Kein Anruf")
            self._btn_hangup.setEnabled(False)

        # Agenten laden
        agents = data.get("available_agents", [])
        self._agent_combo.clear()
        for agent in agents:
            self._agent_combo.addItem(agent)
        active = data.get("active_agent")
        if active:
            idx = self._agent_combo.findText(active)
            if idx >= 0:
                self._agent_combo.setCurrentIndex(idx)

    def _handle_call_incoming(self, data: dict):
        caller = data.get("caller_id", "Unbekannt")
        self._call_indicator.set_status("warning")
        self._call_label.setText(f"Eingehend: {caller}")
        self._transcript.clear()
        self._add_transcript_line("system", f"Eingehender Anruf von: {caller}")

    def _handle_call_active(self, data: dict):
        caller = data.get("caller_id", "Aktiv")
        agent = data.get("agent", "")
        self._call_indicator.set_status("active")
        self._call_label.setText(f"Anruf aktiv: {caller}")
        self._btn_hangup.setEnabled(True)
        if agent:
            self._add_transcript_line("system", f"Agent: {agent}")

    def _handle_call_ended(self, data: dict):
        reason = data.get("reason", "")
        self._call_indicator.set_status("offline")
        self._call_label.setText("Kein Anruf")
        self._btn_hangup.setEnabled(False)
        self._add_transcript_line("system", f"Anruf beendet: {reason}")

    def _handle_transcript(self, data: dict):
        role = data.get("role", "")
        text = data.get("text", "")
        is_final = data.get("is_final", False)

        if text and is_final:
            self._add_transcript_line(role, text)

    def _handle_order_update(self, data: dict):
        order = data.get("order", {})
        items = order.get("items", [])

        self._order_list.clear()
        for item in items:
            text = f"{item.get('menge', 0)}x {item.get('produktname', '')} ({item.get('kennung', '')})"
            self._order_list.addItem(text)

        total = order.get("total_quantity", 0)
        count = order.get("item_count", 0)
        self._order_summary.setText(f"Bestellung: {count} Positionen, {total} Stueck")

    def _handle_function_call(self, data: dict):
        name = data.get("name", "")
        self._add_debug(f"[Function Call] {name}")

    def _handle_function_result(self, data: dict):
        name = data.get("name", "")
        result = data.get("result", "")
        self._add_debug(f"[Function Result] {name}: {result[:100]}")

    def _handle_agent_changed(self, data: dict):
        old = data.get("old_agent", "")
        new = data.get("new_agent", "")
        self._add_transcript_line("system", f"Agent gewechselt: {old} -> {new}")

        idx = self._agent_combo.findText(new)
        if idx >= 0:
            self._agent_combo.blockSignals(True)
            self._agent_combo.setCurrentIndex(idx)
            self._agent_combo.blockSignals(False)

    def _handle_firewall_status(self, data: dict):
        enabled = data.get("enabled", True)
        self._fw_label.setText(f"Status: {'Aktiv' if enabled else 'DEAKTIVIERT'}")

    def _handle_debug_event(self, data: dict):
        event = data.get("event", {})
        self._add_debug(f"[Event] {event.get('type', '')} {json.dumps(event.get('data', {}), ensure_ascii=False)[:150]}")

    # ============== UI Helpers ==============

    def _add_transcript_line(self, role: str, text: str):
        colors = {
            "caller": "#89b4fa",
            "assistant": "#a6e3a1",
            "system": "#6c7086",
        }
        color = colors.get(role, "#cdd6f4")
        prefix = {"caller": "Anrufer", "assistant": "AI", "system": "System"}.get(role, role)

        self._transcript.append(
            f'<span style="color: {color}; font-weight: bold;">[{prefix}]</span> '
            f'<span style="color: #cdd6f4;">{text}</span>'
        )

    def _add_debug(self, text: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._debug_log.append(f"<span style='color: #6c7086;'>{ts}</span> {text}")

    # ============== Button Handlers ==============

    def _on_hangup(self):
        self._ws_client.send({"type": "hangup"})

    def _on_mute_toggle(self, muted: bool):
        if muted:
            self._ws_client.send({"type": "mute_ai"})
            self._btn_mute.setText("Unmute")
        else:
            self._ws_client.send({"type": "unmute_ai"})
            self._btn_mute.setText("Stumm")

    def _on_agent_changed(self, agent_name: str):
        if agent_name:
            self._ws_client.send({"type": "switch_agent", "agent_name": agent_name})

    def closeEvent(self, event):
        """Beim Schliessen WebSocket trennen."""
        self._ws_client.stop()
        event.accept()


def run_gui(host: str = "localhost", port: int = 8085):
    """Startet die Qt GUI."""
    api_url = f"ws://{host}:{port}/ws"

    app = QApplication(sys.argv)
    app.setApplicationName("VoiceAgent Platform")
    app.setStyle("Fusion")

    window = MainWindow(api_url=api_url)
    window.show()

    sys.exit(app.exec())
