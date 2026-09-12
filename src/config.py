import os
import sys
import json
import logging
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any, List, Optional

logger = logging.getLogger(__name__)

PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat"
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "google/gemini-2.5-flash:free"
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini"
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-8b-instant"
    }
}

@dataclass
class PipelineConfig:
    """
    Configuration settings for the automated file-driven AI pipeline.
    """
    watch_directories: List[str] = field(default_factory=lambda: [os.getcwd()])
    watch_directory: Optional[str] = None
    
    allowed_extensions: Tuple[str, ...] = ('.txt', '.json', '.md', '.csv', '.log', '.pdf')
    ignored_extensions: Tuple[str, ...] = ('.tmp', '.part', '.crdownload', '.swp', '.lock')
    
    stability_timeout: int = 30
    stability_poll_interval: float = 0.5
    
    provider: str = "openrouter"
    api_key: str = field(default_factory=lambda: os.environ.get("AI_API_KEY", "your-api-key-here"))
    base_url: str = field(default_factory=lambda: os.environ.get("AI_BASE_URL", "https://openrouter.ai/api/v1"))
    model_name: str = field(default_factory=lambda: os.environ.get("AI_MODEL", "google/gemini-2.5-flash:free"))
    
    num_workers: int = 2
    max_retries: int = 3
    backoff_factor: float = 1.5
    max_backoff_delay: float = 30.0
    max_payload_length: int = 4000
    enable_wrapup: bool = False
    update_clients_docx: bool = False
    
    def __post_init__(self):
        if self.watch_directory:
            self.watch_directories = [self.watch_directory]
        elif self.watch_directories:
            self.watch_directory = self.watch_directories[0]

    def apply_provider_preset(self, provider_name: str):
        provider_name = provider_name.lower()
        if provider_name in PROVIDER_PRESETS:
            preset = PROVIDER_PRESETS[provider_name]
            self.provider = provider_name
            if not os.environ.get("AI_BASE_URL"):
                self.base_url = preset["base_url"]
            if not os.environ.get("AI_MODEL"):
                self.model_name = preset["default_model"]

    @classmethod
    def load(cls, settings_file: str = "settings.json") -> "PipelineConfig":
        """
        Loads configuration from settings.json if present, merged with environment variables.
        """
        config = cls()
        
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if "watch_directories" in data and isinstance(data["watch_directories"], list):
                    config.watch_directories = data["watch_directories"]
                    config.watch_directory = config.watch_directories[0] if config.watch_directories else os.getcwd()
                elif "watch_directory" in data:
                    config.watch_directories = [data["watch_directory"]]
                    config.watch_directory = data["watch_directory"]

                if "provider" in data:
                    config.apply_provider_preset(data["provider"])
                if "api_key" in data:
                    config.api_key = data["api_key"]
                if "base_url" in data:
                    config.base_url = data["base_url"]
                if "model_name" in data:
                    config.model_name = data["model_name"]
                if "num_workers" in data:
                    config.num_workers = int(data["num_workers"])
                if "stability_timeout" in data:
                    config.stability_timeout = int(data["stability_timeout"])
                if "enable_wrapup" in data:
                    config.enable_wrapup = bool(data["enable_wrapup"])
                if "update_clients_docx" in data:
                    config.update_clients_docx = bool(data["update_clients_docx"])

                logger.info(f"Loaded configuration settings from {settings_file}")
            except Exception as e:
                logger.error(f"Error loading {settings_file}: {e}")

        # Environment variable overrides
        if os.environ.get("WATCH_DIR"):
            config.watch_directories = [os.environ.get("WATCH_DIR")]
            config.watch_directory = os.environ.get("WATCH_DIR")
        if os.environ.get("AI_API_KEY"):
            config.api_key = os.environ.get("AI_API_KEY")
        if os.environ.get("AI_PROVIDER"):
            config.apply_provider_preset(os.environ.get("AI_PROVIDER"))
        if os.environ.get("ENABLE_WRAPUP"):
            config.enable_wrapup = os.environ.get("ENABLE_WRAPUP").lower() in ("true", "1", "yes")
            
        return config

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        return cls.load("settings.json")
