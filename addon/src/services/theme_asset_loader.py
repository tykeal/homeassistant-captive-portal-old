# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Theme asset loader for loading and caching theme templates."""

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class ThemeAssetLoader:
    """Loads and manages theme assets (templates, static files)."""

    def __init__(self, themes_dir: str | Path | None = None):
        """Initialize the theme asset loader.

        Args:
            themes_dir: Path to themes directory. If None, uses default location.
        """
        if themes_dir is None:
            # Default to src/themes directory
            current_dir = Path(__file__).parent.parent
            self.themes_dir = current_dir / "themes"
        else:
            self.themes_dir = Path(themes_dir)

        self.default_theme = "default"
        self._jinja_env: Environment | None = None
        self._theme_metadata_cache: dict[str, dict[str, Any]] = {}

        logger.debug("Theme asset loader initialized", themes_dir=str(self.themes_dir))

    def _get_jinja_env(self) -> Environment:
        """Get or create Jinja2 environment for template rendering.

        Returns:
            Jinja2 environment
        """
        if self._jinja_env is None:
            self._jinja_env = Environment(
                loader=FileSystemLoader(str(self.themes_dir)),
                autoescape=True,
                auto_reload=False,  # For production, disable auto-reload
            )
            logger.debug("Jinja2 environment created")

        return self._jinja_env

    def get_theme_template(
        self, theme_name: str | None = None, template_name: str = "portal.html"
    ) -> str:
        """Get the path to a theme template.

        Args:
            theme_name: Name of the theme. If None, uses default theme.
            template_name: Name of the template file

        Returns:
            Template path relative to themes directory

        Raises:
            FileNotFoundError: If theme or template not found
        """
        theme = theme_name or self.default_theme
        template_path = f"{theme}/{template_name}"

        # Verify template exists
        full_path = self.themes_dir / theme / template_name
        if not full_path.exists():
            logger.warning(
                "Theme template not found, falling back to default",
                theme=theme,
                template=template_name,
            )
            # Fallback to default theme
            if theme != self.default_theme:
                return self.get_theme_template(
                    theme_name=self.default_theme, template_name=template_name
                )
            raise FileNotFoundError(
                f"Theme template not found: {template_path} and no default available"
            )

        return template_path

    def render_template(
        self,
        theme_name: str | None = None,
        template_name: str = "portal.html",
        **context: Any,
    ) -> str:
        """Render a theme template with the given context.

        Args:
            theme_name: Name of the theme. If None, uses default theme.
            template_name: Name of the template file
            **context: Template context variables

        Returns:
            Rendered HTML

        Raises:
            TemplateNotFound: If template cannot be found even with fallback
        """
        try:
            template_path = self.get_theme_template(theme_name, template_name)
            env = self._get_jinja_env()
            template = env.get_template(template_path)
            return template.render(**context)

        except TemplateNotFound as e:
            logger.error(
                "Failed to render template",
                theme=theme_name,
                template=template_name,
                error=str(e),
            )
            raise

    def get_theme_metadata(self, theme_name: str | None = None) -> dict[str, Any]:
        """Get theme metadata from theme.yaml.

        Args:
            theme_name: Name of the theme. If None, uses default theme.

        Returns:
            Theme metadata dictionary

        Raises:
            FileNotFoundError: If theme metadata file not found
        """
        theme = theme_name or self.default_theme

        # Check cache
        if theme in self._theme_metadata_cache:
            return self._theme_metadata_cache[theme]

        # Load metadata file
        metadata_path = self.themes_dir / theme / "theme.yaml"
        if not metadata_path.exists():
            logger.warning(
                "Theme metadata not found, using defaults",
                theme=theme,
                metadata_path=str(metadata_path),
            )
            # Return default metadata
            return {
                "name": theme,
                "version": "unknown",
                "description": "No description available",
                "template": "portal.html",
            }

        try:
            with open(metadata_path) as f:
                metadata = yaml.safe_load(f)

            # Cache metadata
            self._theme_metadata_cache[theme] = metadata
            logger.debug("Theme metadata loaded", theme=theme)

            return metadata

        except yaml.YAMLError as e:
            logger.error("Failed to parse theme metadata", theme=theme, error=str(e))
            raise ValueError(f"Invalid theme metadata for {theme}: {e}") from e

    def list_available_themes(self) -> list[str]:
        """List all available themes in the themes directory.

        Returns:
            List of theme names
        """
        if not self.themes_dir.exists():
            logger.warning("Themes directory does not exist", dir=str(self.themes_dir))
            return []

        themes = []
        for item in self.themes_dir.iterdir():
            if item.is_dir() and (item / "portal.html").exists():
                themes.append(item.name)

        logger.debug("Available themes", themes=themes)
        return themes

    def validate_theme(self, theme_name: str) -> bool:
        """Validate that a theme has all required assets.

        Args:
            theme_name: Name of the theme to validate

        Returns:
            True if theme is valid, False otherwise
        """
        theme_path = self.themes_dir / theme_name

        # Check theme directory exists
        if not theme_path.exists() or not theme_path.is_dir():
            logger.warning("Theme directory not found", theme=theme_name)
            return False

        # Check required template exists
        template_path = theme_path / "portal.html"
        if not template_path.exists():
            logger.warning("Theme missing required template", theme=theme_name)
            return False

        # Optionally check metadata
        metadata_path = theme_path / "theme.yaml"
        if metadata_path.exists():
            try:
                self.get_theme_metadata(theme_name)
            except (ValueError, yaml.YAMLError):
                logger.warning("Theme has invalid metadata", theme=theme_name)
                return False

        logger.debug("Theme validation passed", theme=theme_name)
        return True

    def get_default_theme_path(self) -> Path:
        """Get the path to the default theme directory.

        Returns:
            Path to default theme
        """
        return self.themes_dir / self.default_theme

    def clear_cache(self) -> None:
        """Clear all cached theme data."""
        self._theme_metadata_cache.clear()
        self._jinja_env = None
        logger.debug("Theme cache cleared")


# Global theme asset loader instance
_theme_asset_loader: ThemeAssetLoader | None = None


def get_theme_asset_loader(themes_dir: str | Path | None = None) -> ThemeAssetLoader:
    """Get the global theme asset loader instance.

    Args:
        themes_dir: Path to themes directory (only used on first call)

    Returns:
        Global theme asset loader instance
    """
    global _theme_asset_loader
    if _theme_asset_loader is None:
        _theme_asset_loader = ThemeAssetLoader(themes_dir)
    return _theme_asset_loader
