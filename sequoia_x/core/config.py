"""配置管理模块：通过 pydantic-settings 从环境变量或 .env 文件加载系统配置。"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_path: str = "data/sequoia_v2.db"
    start_date: str = "2024-01-01"
    qq_bot_api_url: str
    qq_target_type: Literal["group", "private"] = "group"
    qq_target_id: int
    qq_bot_access_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """返回全局 Settings 单例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
