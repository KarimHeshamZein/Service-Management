"""Compatibility exports for the shared machine-profile store."""

from app.machine_config.profile_store import (
    MachineProfileError,
    load_profile,
    save_profile,
)
from app.machine_config.env_file import read_env_file


def reconcile_runtime_profile(paths) -> dict:
    """Make the running service port authoritative for local Console settings."""
    environment = read_env_file(paths.env_file)
    try:
        runtime_port = int(environment.get("APP_PORT", "8993"))
    except ValueError:
        raise MachineProfileError("APP_PORT in the installed environment is invalid.") from None
    if not 1 <= runtime_port <= 65535:
        raise MachineProfileError("APP_PORT in the installed environment is invalid.")

    profile_exists = paths.machine_settings.is_file()
    profile = load_profile(paths.machine_settings)
    changed = not profile_exists
    for field in ("public_port", "local_port", "internal_port"):
        if profile.get(field) != runtime_port:
            profile[field] = runtime_port
            changed = True
    if not profile_exists:
        profile["backup_directory"] = str(paths.backups / "scheduled")
    if changed:
        save_profile(paths.machine_settings, profile)
    return profile

__all__ = [
    "MachineProfileError",
    "load_profile",
    "reconcile_runtime_profile",
    "save_profile",
]
