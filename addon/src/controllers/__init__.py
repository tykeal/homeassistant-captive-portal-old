# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Controller adapters for network access provisioning."""

from .base import ControllerAdapter, ProvisionResult
from .omada import OmadaController

__all__ = ["ControllerAdapter", "ProvisionResult", "OmadaController"]
