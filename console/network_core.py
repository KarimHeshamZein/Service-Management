"""Transactional Windows adapter, endpoint and firewall configuration."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from app.machine_config.endpoints import endpoint_updates
from app.machine_config.env_file import update_env_file
from app.machine_config.firewall import apply_firewall_rules, expected_rules
from app.machine_config.ports import check_port
from app.machine_config.validation import validate_network

from .config_store import load_profile, save_profile
from .paths import InstallPaths
from .service_core import ServiceController


class NetworkOperationError(RuntimeError):
    """A Windows network change failed or could not be rolled back."""


class NetworkController:
    def __init__(
        self,
        paths: InstallPaths,
        service: ServiceController,
        *,
        runner: Callable[..., Any] = subprocess.run,
        env_writer=update_env_file,
        firewall_writer=apply_firewall_rules,
    ) -> None:
        self.paths = paths
        self.service = service
        self.runner = runner
        self.env_writer = env_writer
        self.firewall_writer = firewall_writer
        self.rollback_path = paths.program_data / "network-rollback.json"

    def adapters(self) -> tuple[str, ...]:
        script = (
            "@(Get-NetAdapter | Where-Object Status -ne 'Disabled' | "
            "Select-Object -ExpandProperty Name) | ConvertTo-Json -Compress"
        )
        result = self._powershell(script)
        if result.returncode != 0:
            return ()
        try:
            value = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return ()
        return tuple(value if isinstance(value, list) else [value])

    def test(self, values: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        current = load_profile(self.paths.machine_settings)
        profile, errors = validate_network(values, base=current)
        if profile.get("local_interface") not in self.adapters():
            errors["local_interface"] = "Select an active Windows network adapter."
        old_port = int(current["internal_port"])
        new_port = int(profile["internal_port"] or 0)
        if new_port and new_port != old_port:
            port_status = check_port(new_port)
            if not port_status.available:
                errors["internal_port"] = port_status.message
        return profile, errors

    def apply(self, values: Mapping[str, Any]) -> None:
        old_profile = load_profile(self.paths.machine_settings)
        profile, errors = self.test(values)
        if errors:
            raise NetworkOperationError(next(iter(errors.values())))
        adapter_state = self._adapter_state(profile["local_interface"])
        _atomic_json(
            self.rollback_path,
            {"profile": old_profile, "adapter": adapter_state},
        )
        try:
            self._apply_adapter(profile)
            if not profile["configure_static_local_ip"]:
                current_state = self._adapter_state(profile["local_interface"])
                addresses = current_state.get("addresses") or []
                if not addresses:
                    raise NetworkOperationError("DHCP did not provide an IPv4 address.")
                profile = {**profile, "local_ip": addresses[0]["address"]}
            save_profile(self.paths.machine_settings, profile)
            self.env_writer(self.paths.env_file, endpoint_updates(profile))
            self.firewall_writer(expected_rules(profile))
            self.service.restart()
            if not self.service.health_checker(int(profile["internal_port"])):
                raise NetworkOperationError("The application health check failed.")
        except Exception:
            self.rollback()
            raise NetworkOperationError(
                "The network change failed; the previous configuration was restored."
            ) from None

    def rollback(self) -> None:
        try:
            value = json.loads(self.rollback_path.read_text(encoding="utf-8"))
            profile = value["profile"]
            self._restore_adapter(value["adapter"])
            save_profile(self.paths.machine_settings, profile)
            self.env_writer(self.paths.env_file, endpoint_updates(profile))
            self.firewall_writer(expected_rules(profile))
            self.service.restart()
        except Exception:
            raise NetworkOperationError(
                "Network rollback failed. Use the saved rollback file and Windows console."
            ) from None

    def _adapter_state(self, adapter: str) -> dict[str, Any]:
        environment = os.environ.copy()
        environment["SMS_NETWORK_ADAPTER"] = adapter
        result = self._powershell(_CAPTURE_SCRIPT, environment)
        if result.returncode != 0:
            raise NetworkOperationError("The selected adapter state could not be read.")
        try:
            value = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            raise NetworkOperationError("Windows returned malformed adapter state.") from None
        if not isinstance(value, dict):
            raise NetworkOperationError("Windows returned malformed adapter state.")
        return value

    def _apply_adapter(self, profile: Mapping[str, Any]) -> None:
        environment = os.environ.copy()
        environment["SMS_NETWORK_PROFILE"] = json.dumps(profile, separators=(",", ":"))
        result = self._powershell(_APPLY_SCRIPT, environment)
        if result.returncode != 0:
            raise NetworkOperationError("Windows could not apply the adapter settings.")

    def _restore_adapter(self, state: Mapping[str, Any]) -> None:
        environment = os.environ.copy()
        environment["SMS_NETWORK_STATE"] = json.dumps(state, separators=(",", ":"))
        result = self._powershell(_RESTORE_SCRIPT, environment)
        if result.returncode != 0:
            raise NetworkOperationError("Windows could not restore the adapter settings.")

    def _powershell(self, script: str, environment=None):
        return self.runner(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env=environment or os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".sms-network-", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


_CAPTURE_SCRIPT = r"""
$name = $env:SMS_NETWORK_ADAPTER
$interface = Get-NetIPInterface -InterfaceAlias $name -AddressFamily IPv4 -ErrorAction Stop
$addresses = @(Get-NetIPAddress -InterfaceAlias $name -AddressFamily IPv4 -ErrorAction Stop |
  Where-Object IPAddress -notlike '169.254.*' | ForEach-Object {
    [ordered]@{address=$_.IPAddress; prefix=[int]$_.PrefixLength}
  })
$gateway = @(Get-NetRoute -InterfaceAlias $name -AddressFamily IPv4 `
  -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
  Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty NextHop)
$dns = @((Get-DnsClientServerAddress -InterfaceAlias $name -AddressFamily IPv4).ServerAddresses)
[ordered]@{adapter=$name; dhcp=([string]$interface.Dhcp -eq 'Enabled');
  addresses=$addresses; gateway=($gateway | Select-Object -First 1); dns=$dns} |
  ConvertTo-Json -Compress -Depth 5
"""

_APPLY_SCRIPT = r"""
$profile = $env:SMS_NETWORK_PROFILE | ConvertFrom-Json
$name = [string]$profile.local_interface
$adapter = Get-NetAdapter -Name $name -ErrorAction Stop
if ($adapter.Status -eq 'Disabled') { throw 'The selected adapter is disabled.' }
if ([bool]$profile.configure_static_local_ip) {
  Set-NetIPInterface -InterfaceAlias $name -AddressFamily IPv4 -Dhcp Disabled
  Get-NetIPAddress -InterfaceAlias $name -AddressFamily IPv4 -PrefixOrigin Manual `
    -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false
  $arguments = @{InterfaceAlias=$name; AddressFamily='IPv4';
    IPAddress=[string]$profile.local_ip; PrefixLength=[int]$profile.local_prefix_length}
  if ($profile.local_gateway) { $arguments.DefaultGateway=[string]$profile.local_gateway }
  New-NetIPAddress @arguments | Out-Null
  $dns = @([string]$profile.local_dns_servers -split "`n" | Where-Object { $_ })
  if ($dns.Count) { Set-DnsClientServerAddress -InterfaceAlias $name -ServerAddresses $dns }
} else {
  Set-NetIPInterface -InterfaceAlias $name -AddressFamily IPv4 -Dhcp Enabled
  Set-DnsClientServerAddress -InterfaceAlias $name -ResetServerAddresses
}
"""

_RESTORE_SCRIPT = r"""
$state = $env:SMS_NETWORK_STATE | ConvertFrom-Json
$name = [string]$state.adapter
if ([bool]$state.dhcp) {
  Set-NetIPInterface -InterfaceAlias $name -AddressFamily IPv4 -Dhcp Enabled
  Set-DnsClientServerAddress -InterfaceAlias $name -ResetServerAddresses
} else {
  Set-NetIPInterface -InterfaceAlias $name -AddressFamily IPv4 -Dhcp Disabled
  Get-NetIPAddress -InterfaceAlias $name -AddressFamily IPv4 -PrefixOrigin Manual `
    -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false
  foreach ($address in @($state.addresses)) {
    $arguments = @{InterfaceAlias=$name; AddressFamily='IPv4';
      IPAddress=[string]$address.address; PrefixLength=[int]$address.prefix}
    if ($state.gateway -and $address -eq @($state.addresses)[0]) {
      $arguments.DefaultGateway=[string]$state.gateway
    }
    New-NetIPAddress @arguments | Out-Null
  }
  if (@($state.dns).Count) {
    Set-DnsClientServerAddress -InterfaceAlias $name -ServerAddresses @($state.dns)
  }
}
"""
