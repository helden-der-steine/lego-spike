# `src/` Layout

- **`robot/`** — Pybricks hub modules (`hardware`, `navigation`, `sir_simulation`, `controller`).
- **`host/`** — Host PC BLE controller & telemetry logger (`python -m host`, `python -m host.log_saver`).
- **`shared/`** — Pure-Python config and BLE protocol shared by both `robot/` and `host/`.
- **`test/`** — Offline unit tests (`uv run python -m unittest discover -s src/test -p "test_*.py"`).

## Why `agent_robot.py` and `color_sensor_logger.py` are directly in `src/`

These two files are the **Pybricks hub entrypoint scripts** deployed via `pybricksdev run ble`.
Because `pybricksdev` does not support `-m <module>` and resolves imports relative to the directory of the target `.py` file, placing both entrypoints directly in `src/` allows `pybricksdev` to bundle both `robot/` and `shared/` onto the SPIKE Prime hubs.
