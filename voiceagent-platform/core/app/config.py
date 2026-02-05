"""
VoiceAgent Platform - Zentrale Konfiguration
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # OpenAI
    OPENAI_API_KEY: str = ""

    # SIP
    SIP_USER: str = ""
    SIP_PASSWORD: str = ""
    SIP_SERVER: str = "sipconnect.sipgate.de"
    SIP_PORT: int = 5060
    SIP_PUBLIC_IP: str = ""  # Oeffentliche Server-IP fuer NAT

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8085
    API_KEY: str = ""  # Optional: API-Key fuer Authentifizierung

    # Database
    DATABASE_URL: str = "sqlite:///app/data/voiceagent.db"
    DATABASE_PATH: str = "/app/data/voiceagent.db"

    # Audio
    SAMPLE_RATE_SIP: int = 48000   # PJSIP mit Opus
    SAMPLE_RATE_AI_INPUT: int = 16000   # OpenAI Input
    SAMPLE_RATE_AI_OUTPUT: int = 24000  # OpenAI Output

    # Agents
    AGENTS_DIR: str = "/app/agents"

    # Code-Sandbox (Legacy, wird durch Claude CLI ersetzt)
    SANDBOX_ENABLED: bool = True
    SANDBOX_TIMEOUT: int = 300  # 5 Minuten
    SANDBOX_MEM_LIMIT: str = "2g"
    SANDBOX_CPU_LIMIT: float = 2.0
    WORKSPACE_DIR: str = "/app/workspace"

    # Claude Coding Agent (CLI mit MAX Account)
    CLAUDE_MODEL: str = "claude-opus-4-6"
    CLAUDE_MAX_TURNS: int = 50  # Max Iterationen pro Aufgabe
    CLAUDE_ALLOWED_TOOLS: list[str] = [
        "Read", "Edit", "Write", "Glob", "Grep",
        "Bash(python *)", "Bash(npm *)", "Bash(node *)",
        "Bash(pip install *)", "Bash(pytest *)", "Bash(git *)",
        "Bash(ls *)", "Bash(mkdir *)", "Bash(cat *)",
    ]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json oder text

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
