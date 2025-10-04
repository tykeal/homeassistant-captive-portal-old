# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for log redaction of credentials and secrets."""

from src.core.logging_config import redact_sensitive_data


def test_redact_password_field():
    """Test that password fields are redacted."""
    record = {
        "message": "User login",
        "username": "testuser",
        "password": "secret123",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["message"] == "User login"
    assert redacted["username"] == "testuser"
    assert redacted["password"] == "[REDACTED]"


def test_redact_token_field():
    """Test that token fields are redacted."""
    record = {
        "action": "API call",
        "api_token": "abc123xyz",
        "access_token": "bearer_token_value",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["action"] == "API call"
    assert redacted["api_token"] == "[REDACTED]"
    assert redacted["access_token"] == "[REDACTED]"


def test_redact_credential_field():
    """Test that credential fields are redacted."""
    record = {
        "event": "portal_auth",
        "voucher_credential": "VOUCHER123",
        "booking_credential": "BOOKING456",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["event"] == "portal_auth"
    assert redacted["voucher_credential"] == "[REDACTED]"
    assert redacted["booking_credential"] == "[REDACTED]"


def test_redact_secret_field():
    """Test that secret fields are redacted."""
    record = {
        "service": "oauth",
        "client_secret": "very_secret_value",
        "api_secret": "another_secret",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["service"] == "oauth"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["api_secret"] == "[REDACTED]"


def test_redact_key_field():
    """Test that key fields are redacted."""
    record = {
        "operation": "encrypt",
        "encryption_key": "aes256key",
        "private_key": "rsa_private_key",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["operation"] == "encrypt"
    assert redacted["encryption_key"] == "[REDACTED]"
    assert redacted["private_key"] == "[REDACTED]"


def test_redact_authorization_field():
    """Test that authorization fields are redacted."""
    record = {
        "request": "GET /api/grants",
        "authorization": "Bearer xyz123",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["request"] == "GET /api/grants"
    assert redacted["authorization"] == "[REDACTED]"


def test_redact_nested_dict():
    """Test that sensitive fields in nested dicts are redacted."""
    record = {
        "event": "user_created",
        "user": {
            "username": "alice",
            "password": "secret",
            "email": "alice@example.com",
        },
        "metadata": {
            "api_key": "key123",
            "source": "admin_panel",
        },
    }

    redacted = redact_sensitive_data(record)

    assert redacted["event"] == "user_created"
    assert redacted["user"]["username"] == "alice"
    assert redacted["user"]["password"] == "[REDACTED]"
    assert redacted["user"]["email"] == "alice@example.com"
    assert redacted["metadata"]["api_key"] == "[REDACTED]"
    assert redacted["metadata"]["source"] == "admin_panel"


def test_redact_list_of_dicts():
    """Test that sensitive fields in list items are redacted."""
    record = {
        "users": [
            {"username": "alice", "password": "alice_pass"},
            {"username": "bob", "auth_token": "bob_token"},
        ]
    }

    redacted = redact_sensitive_data(record)

    assert redacted["users"][0]["username"] == "alice"
    assert redacted["users"][0]["password"] == "[REDACTED]"
    assert redacted["users"][1]["username"] == "bob"
    assert redacted["users"][1]["auth_token"] == "[REDACTED]"


def test_redact_case_insensitive():
    """Test that redaction is case-insensitive."""
    record = {
        "PASSWORD": "secret1",
        "Password": "secret2",
        "API_TOKEN": "token123",
        "Api_Key": "key456",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["PASSWORD"] == "[REDACTED]"
    assert redacted["Password"] == "[REDACTED]"
    assert redacted["API_TOKEN"] == "[REDACTED]"
    assert redacted["Api_Key"] == "[REDACTED]"


def test_redact_partial_match():
    """Test that fields containing sensitive keywords are redacted."""
    record = {
        "user_password": "pass123",
        "oauth_token": "token456",
        "encryption_key_id": "key789",
    }

    redacted = redact_sensitive_data(record)

    assert redacted["user_password"] == "[REDACTED]"
    assert redacted["oauth_token"] == "[REDACTED]"
    assert redacted["encryption_key_id"] == "[REDACTED]"


def test_redact_preserves_non_sensitive():
    """Test that non-sensitive fields are preserved."""
    record = {
        "timestamp": "2025-01-26T10:00:00Z",
        "level": "INFO",
        "message": "Grant provisioned",
        "grant_id": "grant-123",
        "device_id": "device-456",
        "status": "active",
    }

    redacted = redact_sensitive_data(record)

    # All fields should be preserved
    assert redacted == record


def test_redact_empty_dict():
    """Test that empty dict is handled correctly."""
    record = {}

    redacted = redact_sensitive_data(record)

    assert redacted == {}


def test_redact_none_values():
    """Test that None values are preserved."""
    record = {
        "username": "alice",
        "password": None,
        "email": None,
    }

    redacted = redact_sensitive_data(record)

    assert redacted["username"] == "alice"
    assert redacted["password"] == "[REDACTED]"  # Field name is sensitive
    assert redacted["email"] is None


def test_redact_certificate_fields():
    """Test that certificate-related fields are redacted."""
    record = {
        "tls_config": {
            "certificate": "-----BEGIN CERTIFICATE-----",
            "cert_path": "/path/to/cert.pem",
            "private_key": "-----BEGIN PRIVATE KEY-----",
        }
    }

    redacted = redact_sensitive_data(record)

    assert redacted["tls_config"]["certificate"] == "[REDACTED]"
    assert redacted["tls_config"]["cert_path"] == "[REDACTED]"
    assert redacted["tls_config"]["private_key"] == "[REDACTED]"


def test_redact_real_world_voucher_scenario():
    """Test redaction of voucher authentication log."""
    record = {
        "event": "portal_authentication",
        "timestamp": "2025-01-26T10:00:00Z",
        "client_ip": "192.168.1.100",
        "voucher_code": "VOUCHER123",  # Not a sensitive field name
        "device_mac": "AA:BB:CC:DD:EE:FF",
        "result": "success",
        "grant_id": "grant-abc-123",
    }

    redacted = redact_sensitive_data(record)

    # Field names don't match sensitive patterns, so preserved
    assert redacted["event"] == "portal_authentication"
    assert redacted["voucher_code"] == "VOUCHER123"
    assert redacted["device_mac"] == "AA:BB:CC:DD:EE:FF"
    assert redacted["result"] == "success"
    assert redacted["grant_id"] == "grant-abc-123"


def test_redact_real_world_api_key_scenario():
    """Test redaction of API configuration with keys."""
    record = {
        "service": "controller_adapter",
        "controller_type": "omada",
        "controller_url": "https://controller.local",
        "api_key": "super_secret_api_key_123",
        "timeout": 30,
    }

    redacted = redact_sensitive_data(record)

    assert redacted["service"] == "controller_adapter"
    assert redacted["controller_type"] == "omada"
    assert redacted["controller_url"] == "https://controller.local"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["timeout"] == 30
