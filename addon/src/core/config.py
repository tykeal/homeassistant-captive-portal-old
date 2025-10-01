# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Configuration models for the captive portal addon."""

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ControllerConfig(BaseModel):
    """Controller configuration settings."""

    type: Literal["omada"] = "omada"
    url: HttpUrl = Field(
        ..., description="Controller URL (e.g., https://192.168.1.1:8443)"
    )
    username: str = Field(..., description="Controller username")
    password: str = Field(..., description="Controller password")
    site_name: str = Field("Default", description="Site name in controller")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        """Validate controller URL format."""
        parsed = urlparse(str(v))
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid controller URL format")
        return v


class ThemeConfig(BaseModel):
    """Theme configuration settings."""

    portal_title: str = Field(
        "Guest Network Access", description="Title shown on portal page"
    )
    background_color: str = Field("#f5f5f5", description="Background color (hex)")
    primary_color: str = Field(
        "#007bff", description="Primary color for buttons/links (hex)"
    )
    logo_url: HttpUrl | None = Field(None, description="Logo URL (optional)")

    @field_validator("background_color", "primary_color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        """Validate hex color format."""
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Color must be in hex format (#rrggbb)")
        try:
            int(v[1:], 16)
        except ValueError as e:
            raise ValueError("Invalid hex color") from e
        return v


class AddonConfig(BaseModel):
    """Main addon configuration."""

    controller: ControllerConfig
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    log_level: Literal["debug", "info", "warning", "error", "critical"] = "info"

    @classmethod
    def from_supervisor_options(cls) -> "AddonConfig":
        """Load configuration from Home Assistant Supervisor environment.

        Returns:
            Parsed addon configuration

        Raises:
            ValueError: If configuration is invalid
        """
        import json

        # Read from supervisor options (injected as environment variable)
        options_json = os.environ.get("SUPERVISOR_OPTIONS", "{}")
        try:
            options = json.loads(options_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid supervisor options JSON: {e}") from e

        return cls(**options)

    @classmethod
    def from_file(cls, config_path: str = "/data/options.json") -> "AddonConfig":
        """Load configuration from file (for testing/development).

        Args:
            config_path: Path to configuration file

        Returns:
            Parsed addon configuration
        """
        import json

        try:
            with open(config_path) as f:
                options = json.load(f)
        except FileNotFoundError as e:
            raise ValueError(f"Configuration file not found: {config_path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid configuration JSON: {e}") from e

        return cls(**options)


# Global configuration instance (set during startup)
config: AddonConfig | None = None


def get_config() -> AddonConfig:
    """Get the current configuration instance.

    Returns:
        Current addon configuration

    Raises:
        RuntimeError: If configuration not initialized
    """
    if config is None:
        raise RuntimeError("Configuration not initialized. Call load_config() first.")
    return config


def load_config() -> AddonConfig:
    """Load and initialize configuration.

    Returns:
        Loaded configuration
    """
    global config

    # Try supervisor environment first, then file fallback
    try:
        config = AddonConfig.from_supervisor_options()
    except (ValueError, KeyError):
        # Fallback to file for development
        config = AddonConfig.from_file()

    return config
