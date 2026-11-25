---
name: add-config-parameter
description: >-
  Use this skill when adding, renaming, or modifying tunable parameters in
  config.toml so that dataclass models, schema validation, hub config sync,
  and unit/MicroPython checks stay in sync.
---

# Add or Modify a Configuration Parameter

All tunable parameters live in `config.toml` and flow through typed dataclasses (`shared.models`), validation (`shared.config_schema`), and hub code-generation (`host.config_sync`).

## Steps

1. **Edit `config.toml`**
   - Place the parameter under the appropriate section (`[simulation]`, `[navigation]`, `[hardware]`, `[hardware.speaker]`, `[hardware.color_hsv]`, `[host]`, or `[robots.*]`).
   - Use milliseconds (`*_ms`) for all time durations and include a concise inline `#` comment.

2. **Update `src/shared/models.py`**
   - Add the typed field and sensible default value to the matching `@dataclass(frozen=True)` model.
   - Keep `src/shared/models.py` MicroPython-compatible (no `dict`/`list` mutable defaults; use `tuple`, primitives, or `Enum` members from `shared.enums`).

3. **Update `src/shared/config_schema.py`**
   - Validate and normalize the new field inside the corresponding `_validate_*` helper (`_require_bool`, `_require_int`, `_require_float`, `_require_str`, `_require_enum`).
   - Do not add Python 3.10+ `!r` f-string flags or unsupported MicroPython syntax.

4. **Wire into Consumers**
   - Read the new attribute from `SIM_CONFIG`, `NAV_CONFIG`, `HW_CONFIG`, `HOST_CONFIG`, or `CONFIG.robot_for(...)` in `src/shared/sim_config.py`, `src/robot/`, or `src/host/`.
   - If the parameter is an enum value, make sure `src/host/config_sync.py` includes that enum in `ENUM_IMPORTS`.

5. **Sync and Verify**
   - Regenerate `src/shared/generated_config.py` and verify MicroPython compilation + tests:
     ```powershell
     uv run python -m host.config_sync
     uv run python -m unittest discover -s src/test -p "test_*.py" -v
     ```
   - Compile modified hub files (`src/shared/` and `src/robot/`) with `.venv\Scripts\mpy-cross-v5.exe` and `.venv\Scripts\mpy-cross-v6.exe` to confirm no MicroPython syntax errors.
   - Add or update validation assertions in `src/test/test_simulation_offline.py` (`test_config_sync_and_validation`).
