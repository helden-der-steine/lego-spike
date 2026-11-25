"""
Synchronizes `config.toml` into the gitignored Pybricks hub module `src/shared/generated_config.py`.

Run before deploying to hubs (invoked automatically by `deploy_script.ps1`):
    uv run python -m host.config_sync
"""

from dataclasses import fields, is_dataclass
from enum import StrEnum
from pathlib import Path
import tomllib

from shared.config_schema import validate_and_normalize
from shared.models import AppConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"
DEFAULT_GENERATED_PATH = PROJECT_ROOT / "src" / "shared" / "generated_config.py"

MODEL_IMPORTS = (
    "AppConfig",
    "BlueHSVConfig",
    "ColorHSVConfig",
    "GreenHSVConfig",
    "HardwareConfig",
    "HostConfig",
    "NavigationConfig",
    "RedHSVConfig",
    "RobotConfig",
    "SimulationConfig",
    "SpeakerConfig",
    "YellowHSVConfig",
)


ENUM_IMPORTS = ("AgentType", "PortLetter", "Zone")


def _format_value(val: object, indent: int = 0) -> str:
    pad = " " * indent
    inner_pad = " " * (indent + 4)

    if isinstance(val, StrEnum):
        return f"{type(val).__name__}.{val.name}"
    if is_dataclass(val):
        lines = [f"{type(val).__name__}("]
        for f in fields(val):
            rendered = _format_value(getattr(val, f.name), indent + 4)
            lines.append(f"{inner_pad}{f.name}={rendered},")
        lines.append(f"{pad})")
        return "\n".join(lines)
    if isinstance(val, dict):
        if not val:
            return "{}"
        lines = ["{"]
        for k, v in val.items():
            lines.append(f"{inner_pad}{_format_value(k)}: {_format_value(v, indent + 4)},")
        lines.append(pad + "}")
        return "\n".join(lines)
    if isinstance(val, tuple):
        items = ", ".join(_format_value(item) for item in val)
        return f"({items},)" if len(val) == 1 else f"({items})"
    return repr(val)


def load_toml_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Reads and validates `config.toml`, returning an `AppConfig` dataclass."""
    with Path(config_path).open("rb") as f:
        raw = tomllib.load(f)
    return validate_and_normalize(raw)


def sync_hub_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_path: str | Path = DEFAULT_GENERATED_PATH,
) -> Path:
    """Generates `src/shared/generated_config.py` from `config.toml` for Pybricks hubs."""
    config = load_toml_config(config_path)
    enum_imports = ", ".join(ENUM_IMPORTS)
    imports = ",\n    ".join(MODEL_IMPORTS)
    source = (
        '"""AUTO-GENERATED from config.toml by `python -m host.config_sync`. Do not edit."""\n\n'
        f"from shared.enums import {enum_imports}\n"
        f"from shared.models import (\n    {imports},\n)\n\n"
        f"CONFIG = {_format_value(config)}\n"
    )
    out_path = Path(output_path)
    out_path.write_text(source, encoding="utf-8")
    return out_path


def main() -> None:
    out_path = sync_hub_config()
    print(f"[OK] Synced config.toml -> {out_path}")


if __name__ == "__main__":
    main()
