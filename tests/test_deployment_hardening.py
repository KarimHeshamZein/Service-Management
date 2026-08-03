"""Deployment-profile security regression tests."""
import json

from app.deployment_config import (
    audit_json,
    default_profile,
    validate_profile,
    windows_script,
)


def _valid_profile(**overrides):
    profile = default_profile()
    profile.update(
        {
            "public_enabled": True,
            "public_ip": "203.0.113.20",
            "public_port": 8993,
            "allowed_remote_ips": "198.51.100.0/24",
            "local_ip": "192.168.10.50",
            "local_port": 8993,
            "internal_port": 8993,
        }
    )
    profile.update(overrides)
    return profile


def test_public_listener_requires_permitted_remote_networks():
    _, errors = validate_profile(_valid_profile(allowed_remote_ips=""))

    assert "allowed_remote_ips" in errors


def test_tls_profile_is_rejected_until_https_is_supported():
    profile, errors = validate_profile(_valid_profile(tls_enabled=True))

    assert errors["tls_enabled"] == "HTTPS is not available yet. Use HTTP."
    assert json.loads(audit_json(profile))["tls_enabled"] is True


def test_non_tls_profile_preserves_http_script_behavior():
    profile, errors = validate_profile(_valid_profile(tls_enabled=False))
    assert errors == {}

    script = windows_script(profile, version=1)

    assert "Set-EnvValue $envPath 'SESSION_HTTPS_ONLY' 'false'" in script
    assert '"http://${publicIp}:${publicPort}"' in script
    assert "netsh interface portproxy" not in script
    assert "iphlpsvc" not in script


def test_all_application_endpoints_must_use_one_port():
    _, errors = validate_profile(_valid_profile(public_port=9443))

    message = "Use the same application port for local, public and internal access."
    assert errors["public_port"] == message
    assert errors["local_port"] == message
    assert errors["internal_port"] == message
