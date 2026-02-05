#!/usr/bin/env python3
"""VoiceAgent Platform - GUI Starter

Startet die PySide6 GUI-Anwendung.
Verbindet sich automatisch mit dem laufenden VoiceAgent-Server.

Verwendung:
    python start_gui.py [--host HOST] [--port PORT]
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="VoiceAgent Platform GUI")
    parser.add_argument(
        "--host",
        default="localhost",
        help="Server-Host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8085,
        help="Server-Port (default: 8085)"
    )
    args = parser.parse_args()

    # PySide6 Check
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except ImportError:
        print("Fehler: PySide6 ist nicht installiert.")
        print("Installiere mit: pip install PySide6")
        sys.exit(1)

    from gui.main_window import run_gui
    run_gui(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
