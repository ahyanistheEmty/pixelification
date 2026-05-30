from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path


APP_NAME = "pixelification"
CONFIG_FILENAME = "runtime-config.json"


@dataclass(slots=True)
class RuntimeConfig:
    host_os: str
    hardware_acceleration_available: bool
    backend: str


def _config_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def config_path() -> Path:
    return _config_root() / CONFIG_FILENAME


def load_or_create_runtime_config(hardware_acceleration_available: bool) -> RuntimeConfig:
    path = config_path()
    current = RuntimeConfig(
        host_os=platform.system(),
        hardware_acceleration_available=hardware_acceleration_available,
        backend="cupy" if hardware_acceleration_available else "cpu",
    )

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                stored = RuntimeConfig(
                    host_os=str(data.get("host_os", current.host_os)),
                    hardware_acceleration_available=bool(
                        data.get("hardware_acceleration_available", current.hardware_acceleration_available)
                    ),
                    backend=str(data.get("backend", current.backend)),
                )
                if (
                    stored.host_os == current.host_os
                    and stored.hardware_acceleration_available == current.hardware_acceleration_available
                    and stored.backend == current.backend
                ):
                    return stored
        except Exception:
            pass

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(current), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return current
