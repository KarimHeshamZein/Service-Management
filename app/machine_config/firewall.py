"""Firewall rule specifications and per-profile state detection."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

LOCAL_RULE_NAME = "SMS Local HTTP"
PUBLIC_RULE_NAME = "SMS Public HTTP"


@dataclass(frozen=True)
class FirewallRule:
    name: str
    local_address: str
    local_port: int
    remote_addresses: tuple[str, ...]


@dataclass(frozen=True)
class FirewallProfileState:
    state: str
    expected: tuple[FirewallRule, ...]
    missing: tuple[str, ...]
    drifted: tuple[str, ...]
    unexpected: tuple[str, ...]


class FirewallError(RuntimeError):
    """The managed Windows Firewall rules could not be updated safely."""


def expected_rules(profile: Mapping[str, Any]) -> tuple[FirewallRule, ...]:
    """Construct the exact inbound rules required by a validated profile."""
    port = int(profile["internal_port"])
    rules: list[FirewallRule] = []
    # A DHCP installation still needs a LAN rule. "Any" keeps local-subnet
    # access working when Windows renews the adapter address; a configured
    # fixed address remains narrowly scoped to that address.
    local_ip = (
        str(profile.get("local_ip") or "").strip()
        if profile.get("configure_static_local_ip")
        else "Any"
    )
    rules.append(FirewallRule(LOCAL_RULE_NAME, local_ip, port, ("LocalSubnet",)))
    if profile.get("public_enabled"):
        remote = tuple(
            value.strip()
            for value in str(profile.get("allowed_remote_ips") or "").splitlines()
            if value.strip()
        )
        rules.append(
            FirewallRule(
                PUBLIC_RULE_NAME,
                str(profile.get("public_ip") or "").strip(),
                port,
                remote,
            )
        )
    return tuple(rules)


def detect_firewall_state(
    profile: Mapping[str, Any],
    observed: Iterable[Mapping[str, Any]] | None = None,
) -> FirewallProfileState:
    """Compare current Windows rules with one validated deployment profile."""
    expected = expected_rules(profile)
    actual = tuple(observed) if observed is not None else read_firewall_rules()
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for item in actual:
        by_name.setdefault(str(item.get("name")), []).append(item)
    missing: list[str] = []
    drifted: list[str] = []
    for rule in expected:
        items = by_name.get(rule.name, [])
        if not items:
            missing.append(rule.name)
        elif len(items) != 1 or not _matches(rule, items[0]):
            drifted.append(rule.name)
    expected_names = {rule.name for rule in expected}
    unexpected = sorted(
        name
        for name in by_name
        if name in {LOCAL_RULE_NAME, PUBLIC_RULE_NAME} and name not in expected_names
    )
    state = (
        "configured"
        if not missing and not drifted and not unexpected
        else "missing"
        if missing
        else "drifted"
    )
    return FirewallProfileState(
        state,
        expected,
        tuple(missing),
        tuple(drifted),
        tuple(unexpected),
    )


def read_firewall_rules() -> tuple[dict[str, Any], ...]:
    """Read the two managed firewall rules through a fixed PowerShell query."""
    script = r"""
$ErrorActionPreference = 'Stop'
$managedNames = @('SMS Local HTTP', 'SMS Public HTTP')
$rules = @(Get-NetFirewallRule -ErrorAction Stop |
  Where-Object { $_.DisplayName -in $managedNames -and $_.Enabled -eq 'True' })
$items = foreach ($rule in $rules) {
  $port = $rule | Get-NetFirewallPortFilter
  $address = $rule | Get-NetFirewallAddressFilter
  [ordered]@{name=[string]$rule.DisplayName; protocol=[string]$port.Protocol;
    local_port=[string]$port.LocalPort; local_address=@($address.LocalAddress);
    remote_addresses=@($address.RemoteAddress); direction=[string]$rule.Direction;
    action=[string]$rule.Action}
}
@($items) | ConvertTo-Json -Compress
"""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        creationflags=flags,
    )
    if result.returncode != 0:
        raise OSError("Windows Firewall state could not be read.")
    parsed = json.loads(result.stdout or "[]")
    return tuple(parsed if isinstance(parsed, list) else [parsed])


def apply_firewall_rules(
    rules: Iterable[FirewallRule],
    *,
    runner=subprocess.run,
) -> None:
    """Replace only the two application-managed inbound firewall rules."""
    payload = json.dumps(
        {
            "rules": [
                {
                    "name": rule.name,
                    "local_address": rule.local_address,
                    "local_port": rule.local_port,
                    "remote_addresses": list(rule.remote_addresses),
                }
                for rule in rules
            ]
        },
        separators=(",", ":"),
    )
    script = r"""
$ErrorActionPreference = 'Stop'
$config = $env:SMS_FIREWALL_RULES | ConvertFrom-Json
$rules = @($config.rules)
$managedNames = @('SMS Local HTTP', 'SMS Public HTTP')
Get-NetFirewallRule -ErrorAction Stop |
  Where-Object { $_.DisplayName -in $managedNames } |
  Remove-NetFirewallRule -ErrorAction Stop
foreach ($rule in $rules) {
  New-NetFirewallRule -DisplayName ([string]$rule.name) -Direction Inbound `
    -Action Allow -Protocol TCP -LocalAddress ([string]$rule.local_address) `
    -LocalPort ([int]$rule.local_port) -RemoteAddress @($rule.remote_addresses) |
    Out-Null
}
"""
    environment = os.environ.copy()
    environment["SMS_FIREWALL_RULES"] = payload
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = runner(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        creationflags=flags,
    )
    if result.returncode != 0:
        raise FirewallError("Windows Firewall rules could not be updated.")


def _matches(expected: FirewallRule, actual: Mapping[str, Any]) -> bool:
    local_addresses = _values(actual.get("local_address"))
    remote_addresses = _values(actual.get("remote_addresses"))
    return (
        str(actual.get("protocol", "")).upper() in {"TCP", "6"}
        and str(actual.get("direction", "")).lower() == "inbound"
        and str(actual.get("action", "")).lower() == "allow"
        and str(actual.get("local_port")) == str(expected.local_port)
        and {str(value).lower() for value in local_addresses}
        == {expected.local_address.lower()}
        and {str(value).lower() for value in remote_addresses}
        == {value.lower() for value in expected.remote_addresses}
    )


def _values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
