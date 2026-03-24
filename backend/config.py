# -*- coding: utf-8 -*-
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "darwen"

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 15001

    # SEC EDGAR
    sec_user_agent: str = "Darwen darwen@example.com"

    # Logging
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def async_database_url(self) -> str:
        return self.database_url.replace("mysql+pymysql", "mysql+aiomysql")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
