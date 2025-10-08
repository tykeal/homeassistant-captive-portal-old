# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Controller factory for creating controller instances."""

from ..core.config import get_config
from .base import ControllerAdapter
from .omada import OmadaController


def get_controller() -> ControllerAdapter:
    """Get controller instance based on configuration.

    Returns:
        Controller adapter instance
    """
    config = get_config()

    # Currently only TP-Link Omada is supported
    return OmadaController(
        controller_url=str(config.controller.url),
        site_id=config.controller.site_name,
        username=config.controller.username,
        password=config.controller.password,
    )
