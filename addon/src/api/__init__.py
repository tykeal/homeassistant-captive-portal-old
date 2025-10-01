# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""API routers for the captive portal addon."""

from .audit import router as audit_router
from .grants import router as grants_router
from .health import router as health_router
from .theme import router as theme_router
from .vouchers import router as vouchers_router

__all__ = [
    "grants_router",
    "vouchers_router",
    "theme_router",
    "audit_router",
    "health_router",
]
