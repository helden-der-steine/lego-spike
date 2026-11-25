# Pybricks MicroPython Constraints (`src/robot/`, `src/shared/`, `src/run_*.py`)

Code under `src/robot/`, `src/shared/`, and `src/run_*.py` runs on LEGO SPIKE Prime hubs under Pybricks MicroPython (320 KB RAM / 1 MB flash), in addition to host CPython tests.

## Mandatory Compatibility Rules

- **No Host-Only Stdlib Imports in Hub Code**: Never directly import `typing`, `enum`, `dataclasses`, `tomllib`, `pathlib`, or `os` at top level in code executed by the hubs.
  - Import `dataclass`, `IntEnum`, and `StrEnum` from `shared._compat` (which handles `TYPE_CHECKING` and MicroPython fallbacks).
  - Read configuration through `shared.sim_config` (`CONFIG`, `SIM_CONFIG`, `NAV_CONFIG`, `HW_CONFIG`), which falls back to `shared.generated_config` on the hub.
- **MicroPython Syntax Limits (`mpy-cross` v5 & v6)**:
  - Do **not** use `!r`, `!s`, or `!a` conversion flags inside f-strings (use `repr(val)` instead).
  - Do **not** split a single f-string across adjacent implicit string literals (`f"a" f"b"`); use one f-string or `+`.
  - Keep `src/shared/config_schema.py` free of PEP 604 `|` union type syntax in function annotations if it remains importable under `src/shared/`.
- **Pybricks Stub Quirks (`pybricks==4.1.1`)**:
  - Import `Matrix` from `pybricks.tools` first with a `pybricks.geometry` fallback for pre-v3.3 firmware.
  - `PrimeHub` accepts `broadcast_channel` and `observe_channels` and exposes `hub.ble` on hub firmware even though the `pybricks` stub package omits them (preserve the `# type: ignore` annotations on `hub` and `ble` in `src/robot/controller.py`).
- **Entrypoint Placement**:
  - Keep `src/run_robot.py` and `src/run_color_sensor_logger.py` directly inside `src/` so `pybricksdev` sets `proj_dir` to `src/` and bundles both `robot/` and `shared/`.
- **Required Verification After Editing Hub/Shared Code**:
  1. Run `uv run python -m host.config_sync` if `config.toml`, `models.py`, or `config_schema.py` changed.
  2. Compile modified hub files with both `.venv\Scripts\mpy-cross-v5.exe -mno-unicode` and `.venv\Scripts\mpy-cross-v6.exe`.
  3. Run `uv run python -m unittest discover -s src/test -p "test_*.py" -v` (confirming `test_pybricks_module_discovery` passes).
