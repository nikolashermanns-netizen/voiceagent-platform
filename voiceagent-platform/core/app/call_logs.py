#!/usr/bin/env python3
"""Zeigt Transcript und Logs fuer einen bestimmten Call (nach Index)."""
import json
import re
import sqlite3
import sys


def main():
    if len(sys.argv) < 2:
        print("Verwendung: python3 call_logs.py <call_nummer>")
        sys.exit(1)

    conn = sqlite3.connect("/app/data/voiceagent.db")
    conn.row_factory = sqlite3.Row
    calls = conn.execute(
        """SELECT id, caller_id, started_at, ended_at, duration_seconds,
                  cost_cents, transcript, logs
           FROM calls WHERE caller_id IS NOT NULL
           ORDER BY started_at ASC"""
    ).fetchall()

    call_num = int(sys.argv[1])
    if call_num < 1 or call_num > len(calls):
        print(f"Call #{call_num} nicht gefunden. Verfuegbar: #1 - #{len(calls)}")
        sys.exit(1)

    c = calls[call_num - 1]
    caller = c["caller_id"] or ""
    m = re.search(r'"([^"]+)"', caller)
    if m:
        caller = m.group(1)

    dur = c["duration_seconds"] or 0
    cost = c["cost_cents"] or 0
    transcript = []
    try:
        transcript = json.loads(c["transcript"] or "[]")
    except Exception:
        pass
    logs = c["logs"] or ""

    print(f"=== Call #{call_num} ===")
    print(f"Anrufer:  {caller}")
    print(f"Start:    {c['started_at']}")
    print(f"Ende:     {c['ended_at'] or '(laufend)'}")
    print(f"Dauer:    {dur}s")
    print(f"Kosten:   {cost:.2f} ct")
    print()

    if transcript:
        print(f"=== Transcript ({len(transcript)} Zeilen) ===")
        for line in transcript:
            role = line.get("role", "?")
            text = line.get("text", "")
            prefix = {"caller": "Anrufer", "user": "Anrufer", "assistant": "AI"}.get(role, role)
            print(f"[{prefix}] {text}")
        print()
    else:
        print("=== Transcript: (leer) ===")
        print()

    if logs:
        print(f"=== Logs ({len(logs)} Zeichen) ===")
        print(logs)
    else:
        print("=== Logs: (leer) ===")


if __name__ == "__main__":
    main()
