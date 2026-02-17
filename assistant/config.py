"""
Zentrale Konfiguration - liest .env und settings.yaml
"""

import os
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Umgebungsvariablen aus .env"""

    # Home Assistant
    ha_url: str = "http://192.168.1.100:8123"
    ha_token: str = ""

    # MindHome
    mindhome_url: str = "http://192.168.1.100:8099"

    # Ollama
    ollama_url: str = "http://localhost:11434"
    model_fast: str = "qwen2.5:3b"
    model_smart: str = "qwen2.5:14b"

    # MindHome Assistant Server
    assistant_host: str = "0.0.0.0"
    assistant_port: int = 8200

    # Redis + ChromaDB
    redis_url: str = "redis://localhost:6379"
    chroma_url: str = "http://localhost:8100"

    # User
    user_name: str = "Max"
    autonomy_level: int = 2
    language: str = "de"

    # Assistent-Identitaet
    assistant_name: str = "MindHome Assistant"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def load_yaml_config() -> dict:
    """Laedt settings.yaml"""
    config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


# Globale Instanzen
settings = Settings()
yaml_config = load_yaml_config()
