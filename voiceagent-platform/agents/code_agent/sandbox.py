"""
Docker-Sandbox fuer sichere Code-Ausfuehrung.

Fuehrt Code in isolierten Docker-Containern aus mit:
- Kein Netzwerkzugang
- Resource-Limits (CPU, RAM)
- Timeout
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional

from core.app.config import settings

logger = logging.getLogger(__name__)


class SandboxResult:
    """Ergebnis einer Sandbox-Ausfuehrung."""

    def __init__(self, stdout: str = "", stderr: str = "",
                 exit_code: int = 0, timed_out: bool = False):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.timed_out = timed_out

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_string(self) -> str:
        """Gibt das Ergebnis als lesbaren String zurueck."""
        lines = []
        if self.timed_out:
            lines.append("TIMEOUT: Ausfuehrung wurde nach Zeitlimit abgebrochen.")
        if self.stdout:
            lines.append(f"=== AUSGABE ===\n{self.stdout}")
        if self.stderr:
            lines.append(f"=== FEHLER ===\n{self.stderr}")
        if not self.stdout and not self.stderr and not self.timed_out:
            lines.append("(Keine Ausgabe)")
        if self.exit_code != 0:
            lines.append(f"\nExit-Code: {self.exit_code}")
        return "\n".join(lines)


class CodeSandbox:
    """
    Fuehrt Code sicher in einem Docker-Container aus.

    Unterstuetzt: Python, JavaScript (Node.js), Bash
    """

    LANGUAGE_IMAGES = {
        "python": "code-sandbox-python",
        "javascript": "code-sandbox-node",
        "bash": "code-sandbox-bash",
    }

    def __init__(self):
        self.enabled = settings.SANDBOX_ENABLED
        self.timeout = settings.SANDBOX_TIMEOUT
        self.mem_limit = settings.SANDBOX_MEM_LIMIT
        self.cpu_limit = settings.SANDBOX_CPU_LIMIT
        self.workspace_dir = settings.WORKSPACE_DIR

    async def execute(self, code: str, language: str = "python",
                      project_id: str = "default") -> SandboxResult:
        """
        Fuehrt Code in der Sandbox aus.

        Args:
            code: Der auszufuehrende Code
            language: Programmiersprache (python, javascript, bash)
            project_id: Projekt-ID fuer Workspace

        Returns:
            SandboxResult mit stdout, stderr, exit_code
        """
        if not self.enabled:
            return SandboxResult(
                stderr="Sandbox ist deaktiviert.",
                exit_code=1
            )

        if language not in self.LANGUAGE_IMAGES:
            return SandboxResult(
                stderr=f"Sprache '{language}' nicht unterstuetzt. "
                       f"Verfuegbar: {', '.join(self.LANGUAGE_IMAGES.keys())}",
                exit_code=1
            )

        image = self.LANGUAGE_IMAGES[language]
        workspace = os.path.join(self.workspace_dir, project_id)
        os.makedirs(workspace, exist_ok=True)

        # Code-Datei erstellen
        ext = {"python": ".py", "javascript": ".js", "bash": ".sh"}[language]
        code_file = os.path.join(workspace, f"main{ext}")

        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)

        # Docker Command
        cmd_map = {
            "python": f"python /workspace/main.py",
            "javascript": f"node /workspace/main.js",
            "bash": f"bash /workspace/main.sh",
        }

        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",  # Kein Netzwerk
            "--memory", self.mem_limit,
            "--cpus", str(self.cpu_limit),
            "-v", f"{workspace}:/workspace:rw",
            "-w", "/workspace",
            image,
            "sh", "-c", cmd_map[language]
        ]

        logger.info(f"[Sandbox] Fuehre {language} Code aus (Projekt: {project_id})")

        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
                return SandboxResult(
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    exit_code=process.returncode or 0
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return SandboxResult(
                    stderr=f"Timeout nach {self.timeout} Sekunden",
                    exit_code=-1,
                    timed_out=True
                )

        except FileNotFoundError:
            return SandboxResult(
                stderr="Docker ist nicht installiert oder nicht erreichbar.",
                exit_code=1
            )
        except Exception as e:
            logger.error(f"[Sandbox] Fehler: {e}")
            return SandboxResult(stderr=str(e), exit_code=1)

    async def list_files(self, project_id: str = "default") -> list[str]:
        """Listet Dateien im Workspace eines Projekts."""
        workspace = os.path.join(self.workspace_dir, project_id)
        if not os.path.isdir(workspace):
            return []

        files = []
        for root, dirs, filenames in os.walk(workspace):
            for filename in filenames:
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, workspace)
                files.append(rel_path)

        return files

    async def read_file(self, project_id: str, filename: str) -> Optional[str]:
        """Liest eine Datei aus dem Workspace."""
        workspace = os.path.join(self.workspace_dir, project_id)
        filepath = os.path.join(workspace, filename)

        # Sicherheit: Kein Pfad-Traversal
        if not os.path.abspath(filepath).startswith(os.path.abspath(workspace)):
            return None

        if not os.path.isfile(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    async def write_file(self, project_id: str, filename: str, content: str) -> bool:
        """Schreibt eine Datei in den Workspace."""
        workspace = os.path.join(self.workspace_dir, project_id)
        filepath = os.path.join(workspace, filename)

        # Sicherheit: Kein Pfad-Traversal
        if not os.path.abspath(filepath).startswith(os.path.abspath(workspace)):
            return False

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"[Sandbox] Datei schreiben fehlgeschlagen: {e}")
            return False
