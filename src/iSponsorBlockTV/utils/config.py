import json
import logging
import os
import sys
from pathlib import Path
from time import sleep
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Set up logging
logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


class Device(BaseModel):
    """Represents a device configuration with screen ID and timing offset."""

    screen_id: str = Field(..., description="Unique identifier for the screen")
    name: str = Field("", description="Name of the device")
    offset: float = Field(default=0, description="Timing offset in milliseconds")

    model_config = ConfigDict(frozen=True)

    @field_validator("screen_id")
    @classmethod
    def screen_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("No screen id found")
        return v.strip()

    @field_validator("offset")
    @classmethod
    def convert_to_seconds(cls, v: float) -> float:
        return v / 1000


class Config(BaseModel):
    """Application configuration with validation and serialization."""

    data_dir: Path
    devices: List[Device] = Field(default_factory=list)
    apikey: str = ""
    skip_categories: List[str] = Field(default_factory=lambda: ["sponsor"])
    skip_count_tracking: bool = True
    mute_ads: bool = False
    skip_ads: bool = False
    auto_play: bool = True
    join_name: str = "iSponsorBlockTV"

    model_config = ConfigDict(validate_assignment=True)

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.json"

    @classmethod
    def load(cls, data_dir: Path | str) -> 'Config':
        """Create a Config instance from a directory path."""
        data_dir = Path(data_dir) if isinstance(data_dir, str) else data_dir
        try:
            json_str = (data_dir / "config.json").read_text(encoding="utf-8")
            return cls.load_json(json_str, data_dir)
        except FileNotFoundError:
            return cls(data_dir=data_dir)

    @classmethod
    def load_json(cls, json_str: str, data_dir: Path | str) -> 'Config':
        """Load config from a JSON string."""
        data_dir = Path(data_dir) if isinstance(data_dir, str) else data_dir
        try:
            return cls.load_dict(json.loads(json_str), data_dir)
        except json.JSONDecodeError:
            cls._exit_with_message("Invalid JSON")

    @classmethod
    def load_dict(cls, data: dict, data_dir: Path | str) -> 'Config':
        """Load config from a dictionary."""
        data_dir = Path(data_dir) if isinstance(data_dir, str) else data_dir
        from iSponsorBlockTV.constants import config_file_blacklist_keys
        filtered_data = {k: v for k, v in data.items() if k not in config_file_blacklist_keys}
        return cls.model_validate({**filtered_data, 'data_dir': data_dir})

    def _handle_missing_config(self) -> None:
        """Handle missing configuration file scenario."""
        if not self.data_dir.exists():
            if not self._is_docker():
                logger.info("Creating data directory")
                self.data_dir.mkdir(parents=True, exist_ok=True)
            else:
                self._exit_with_message(
                    "Docker configuration error. Please mount the data directory and "
                    "refer to: https://github.com/dmunozv04/iSponsorBlockTV/wiki/Installation#Docker\n"
                    "V2 upgrade required: https://github.com/dmunozv04/iSponsorBlockTV/wiki/Migrate-from-V1-to-V2"
                )
        else:
            logger.info("Using default configuration")
            self.save()

    @staticmethod
    def _is_docker() -> bool:
        """Check if running in Docker environment."""
        return bool(os.getenv("iSPBTV_docker"))

    @staticmethod
    def _exit_with_message(message: str, delay: int = 10) -> None:
        """Exit application with message and optional delay."""
        logger.error(message)
        logger.info(f"Exiting in {delay} seconds...")
        sleep(delay)
        sys.exit(1)

    def validate_config(self) -> None:
        """Perform additional configuration validation."""
        if hasattr(self, "atvs"):
            self._exit_with_message(
                "The 'atvs' config option is deprecated. Please upgrade to V2:\n"
                "https://github.com/dmunozv04/iSponsorBlockTV/wiki/Migrate-from-V1-to-V2"
            )

        if not self.devices:
            self._exit_with_message("No devices found, please add at least one device")

    def save(self) -> None:
        """Save current configuration to file."""
        try:
            config_dict = self.model_dump(exclude={"data_dir"})
            self.config_file.write_text(
                json.dumps(config_dict, indent=4), encoding="utf-8"
            )
        except IOError as e:
            logger.error(f"Failed to save configuration: {e}")

    def __eq__(self, other: object) -> bool:
        """Compare configurations for equality."""
        if not isinstance(other, Config):
            return NotImplemented
        return self.model_dump() == other.model_dump()
