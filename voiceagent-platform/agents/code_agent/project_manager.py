"""
Projekt-Manager fuer Code-Agent.

Verwaltet Workspace-Dateien pro Projekt.
"""

import logging
import os
import json
from datetime import datetime
from typing import Optional

from core.app.config import settings

logger = logging.getLogger(__name__)


class ProjectManager:
    """Verwaltet Projekte und deren Dateien im Workspace."""

    def __init__(self):
        self.workspace_dir = settings.WORKSPACE_DIR
        self._projects_file = os.path.join(self.workspace_dir, "_projects.json")
        self._projects: dict = self._load_projects()

    def _load_projects(self) -> dict:
        """Laedt die Projektliste."""
        try:
            if os.path.exists(self._projects_file):
                with open(self._projects_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Projektliste laden fehlgeschlagen: {e}")
        return {}

    def _save_projects(self):
        """Speichert die Projektliste."""
        try:
            os.makedirs(self.workspace_dir, exist_ok=True)
            with open(self._projects_file, "w", encoding="utf-8") as f:
                json.dump(self._projects, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Projektliste speichern fehlgeschlagen: {e}")

    def create_project(self, project_id: str, name: str,
                       description: str = "") -> dict:
        """Erstellt ein neues Projekt."""
        project_dir = os.path.join(self.workspace_dir, project_id)
        os.makedirs(project_dir, exist_ok=True)

        project = {
            "id": project_id,
            "name": name,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "files": [],
        }
        self._projects[project_id] = project
        self._save_projects()

        logger.info(f"Projekt erstellt: {project_id} ({name})")
        return project

    def get_project(self, project_id: str) -> Optional[dict]:
        """Gibt ein Projekt zurueck."""
        return self._projects.get(project_id)

    def list_projects(self) -> list[dict]:
        """Listet alle Projekte auf."""
        return list(self._projects.values())

    def list_files(self, project_id: str) -> list[str]:
        """Listet Dateien eines Projekts auf."""
        project_dir = os.path.join(self.workspace_dir, project_id)
        if not os.path.isdir(project_dir):
            return []

        files = []
        for root, dirs, filenames in os.walk(project_dir):
            for filename in filenames:
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, project_dir)
                files.append(rel_path)
        return files

    def read_file(self, project_id: str, filename: str) -> Optional[str]:
        """Liest eine Datei."""
        filepath = os.path.join(self.workspace_dir, project_id, filename)

        # Sicherheit
        base = os.path.abspath(os.path.join(self.workspace_dir, project_id))
        if not os.path.abspath(filepath).startswith(base):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    def write_file(self, project_id: str, filename: str, content: str) -> bool:
        """Schreibt eine Datei."""
        filepath = os.path.join(self.workspace_dir, project_id, filename)

        base = os.path.abspath(os.path.join(self.workspace_dir, project_id))
        if not os.path.abspath(filepath).startswith(base):
            return False

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Datei schreiben fehlgeschlagen: {e}")
            return False
