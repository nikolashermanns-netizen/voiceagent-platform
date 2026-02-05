#!/usr/bin/env python3
"""VoiceAgent Platform - GUI Starter

Prueft alle Dependencies und startet die PySide6 GUI-Anwendung.
Verbindet sich automatisch mit dem laufenden VoiceAgent-Server.

Verwendung:
    python start_gui.py [--host HOST] [--port PORT]
"""

import sys
import subprocess
import importlib
import argparse

# Benoetigte Pakete: (import_name, pip_name)
REQUIRED_PACKAGES = [
    ("PySide6", "PySide6"),
    ("websocket", "websocket-client"),
]


def check_python_version():
    """Prueft ob Python >= 3.10 installiert ist."""
    if sys.version_info < (3, 10):
        print(f"Fehler: Python 3.10+ wird benoetigt (installiert: {sys.version})")
        sys.exit(1)
    print(f"  Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} - OK")


def check_and_install_packages():
    """Prueft ob alle Pakete installiert sind und installiert fehlende."""
    missing = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
            print(f"  {pip_name} - OK")
        except ImportError:
            print(f"  {pip_name} - FEHLT")
            missing.append(pip_name)

    if missing:
        print(f"\nFehlende Pakete: {', '.join(missing)}")
        answer = input("Automatisch installieren? [J/n] ").strip().lower()
        if answer in ("", "j", "ja", "y", "yes"):
            for pkg in missing:
                print(f"  Installiere {pkg}...")
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", pkg],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE
                    )
                    print(f"  {pkg} - installiert")
                except subprocess.CalledProcessError as e:
                    print(f"  Fehler bei Installation von {pkg}: {e}")
                    sys.exit(1)
        else:
            print("\nManuelle Installation:")
            print(f"  pip install {' '.join(missing)}")
            sys.exit(1)


def check_dependencies():
    """Fuehrt alle Dependency-Checks durch."""
    print("Pruefe Voraussetzungen...\n")
    check_python_version()
    check_and_install_packages()
    print("\nAlle Voraussetzungen erfuellt.\n")


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
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Dependency-Checks ueberspringen"
    )
    args = parser.parse_args()

    if not args.skip_checks:
        check_dependencies()

    from gui.main_window import run_gui
    run_gui(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
