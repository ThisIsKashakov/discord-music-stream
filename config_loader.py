import json
from typing import Dict, Any


class ConfigError(Exception):
    """Custom exception for configuration errors."""

    pass


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    Loads and validates configuration from a JSON file.

    Args:
        config_path (str): Path to the configuration file. Defaults to "config.json"

    Returns:
        Dict[str, Any]: Validated configuration dictionary

    Raises:
        ConfigError: If configuration is invalid or missing required fields
    """
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        raise ConfigError(f"Error: {config_path} file not found.")
    except json.JSONDecodeError:
        raise ConfigError(f"Error: {config_path} is not a valid JSON file.")
    except Exception as e:
        raise ConfigError(f"Error reading config file: {e}")

    required_config = {
        "DISCORD_TOKEN": str,
        "GUILD_ID": str,
        "VOICE_CHANNEL_ID": str,
        "TEXT_CHANNEL_ID": str,
        "desktop_clients": list,
        "MICROPHONE_ID": str,
        "enable_media_events": bool,
    }

    for key, expected_type in required_config.items():
        if key not in config:
            raise ConfigError(f"Error: '{key}' is missing in {config_path}")

        if config[key] is None or (
            expected_type != bool and not config[key] and key != "desktop_clients"
        ):
            raise ConfigError(f"Error: '{key}' has an empty value in {config_path}")

        if not isinstance(config[key], expected_type):
            raise ConfigError(
                f"Error: '{key}' must be of type {expected_type.__name__} in {config_path}"
            )

    if not config["desktop_clients"]:
        raise ConfigError(
            f"Error: 'desktop_clients' must be a non-empty list in {config_path}"
        )

    numeric_fields = ["GUILD_ID", "VOICE_CHANNEL_ID", "TEXT_CHANNEL_ID"]
    for field in numeric_fields:
        if not config[field].isdigit():
            raise ConfigError(
                f"Error: '{field}' must contain only digits in {config_path}"
            )
        config[field] = int(config[field])

    return config


class Config:
    """Configuration singleton class."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not Config._initialized:
            self._config = None
            Config._initialized = True

    def load(self, config_path: str = "config.json") -> None:
        """Load configuration from file."""
        self._config = load_config(config_path)

    @property
    def config(self) -> Dict[str, Any]:
        """Get configuration dictionary."""
        if self._config is None:
            raise ConfigError("Configuration not loaded. Call load() first.")
        return self._config

    def __getattr__(self, name: str) -> Any:
        """Allow accessing config values as attributes."""
        if self._config is None:
            raise ConfigError("Configuration not loaded. Call load() first.")

        if name in self._config:
            return self._config[name]
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")


config = Config()
