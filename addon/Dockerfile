#!/usr/bin/env -S docker build . --tag ghcr.io/hassio-addons/addon-captive-portal --file
# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

ARG BUILD_FROM=ghcr.io/hassio-addons/base:16.0.1
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Setup base system
ARG BUILD_ARCH=amd64
RUN \
    apk add --no-cache \
        python3=~3.13 \
        py3-pip=~24

# Install uv for fast Python package management
RUN pip3 install --no-cache-dir uv==0.4.29

# Copy source code
COPY src /app/src
COPY pyproject.toml /app/
COPY uv.lock /app/

# Set working directory
WORKDIR /app

# Install Python dependencies using uv
RUN uv sync --frozen --no-dev

# Copy run script
COPY rootfs /

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Labels
LABEL \
    io.hass.name="Captive Portal" \
    io.hass.description="Captive portal for rental guest network access" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="1.0.0" \
    maintainer="Andrew Grimberg <tykeal@bardicgrove.org>" \
    org.opencontainers.image.title="Captive Portal Addon" \
    org.opencontainers.image.description="Home Assistant addon for rental guest network captive portal" \
    org.opencontainers.image.vendor="Home Assistant Community Add-ons" \
    org.opencontainers.image.authors="Andrew Grimberg <tykeal@bardicgrove.org>" \
    org.opencontainers.image.licenses="Apache-2.0" \
    org.opencontainers.image.source="https://github.com/tykeal/homeassistant-captive-portal"

# Expose port
EXPOSE 8000
