from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_hours: int = 8

    database_url: str = "sqlite+aiosqlite:////data/web_terminal.db"

    sandbox_image: str = "web-terminal-sandbox:latest"
    sandbox_network: str = "web_terminal_sandbox"
    container_memory: str = "256m"
    container_cpus: float = 0.5
    container_pids_limit: int = 50

    idle_timeout: int = 1800       # 30 minutes
    max_session_time: int = 14400  # 4 hours
    cleanup_interval: int = 60
    max_sessions_per_user: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
