---
name: calibrate-color-zones
description: >-
  Use this skill when calibrating or updating ColorSensor HSV thresholds for
  arena mats (Yellow, Blue, Green, Red, or dark table borders), or when
  deploying src/run_color_sensor_logger.py to inspect live sensor readings.
---

# Calibrate Arena Color Zones

Zone classification lives in `src/robot/hardware.py` (`detect_zone`) and reads its thresholds from `[hardware.color_hsv]` in `config.toml`.

## Steps

1. **Deploy the Color Sensor Logger to One Hub**
   - Ensure the hub is powered on and disconnected from the Pybricks web app, then run:
     ```powershell
     .\deploy_script.ps1 -ScriptPath src\run_color_sensor_logger.py -RobotIds 1
     ```
   - Alternatively, run `src/run_color_sensor_logger.py` directly from `pybricksdev` if inspecting live console output:
     ```powershell
     .venv\Scripts\pybricksdev.exe run ble --name "Held-1" src\run_color_sensor_logger.py
     ```

2. **Collect HSV Samples**
   - Place the robot over each color zone (**Yellow**, **Blue**, **Green**, **Red**), over zone seams, and over the dark table surface outside the mats.
   - Record the `(h, s, v)` triples printed every `color_logger_sample_interval_ms` (`500 ms` default). Press `Button.LEFT` on the hub to stop logging.

3. **Update `config.toml`**
   - Set `[hardware.color_hsv].min_zone_value` just above the highest `V` observed on dark table borders/seams (so borders return `None` and trigger edge avoidance).
   - Update `[hardware.color_hsv.Red]` (`hue_low_max`, `hue_high_min` for `0°/360°` wraparound, `min_saturation`) and the `Yellow`, `Green`, and `Blue` HSV bounds so all 4 zones are cleanly separated.

4. **Update Regression Tests & Verify**
   - Add representative `(H, S, V)` readings (including dark edge readings expecting `None`) to `test_detect_zone_new_paper_hsv` in `src/test/test_simulation_offline.py`.
   - Sync hub config and run the test suite:
     ```powershell
     uv run python -m host.config_sync
     uv run python -m unittest discover -s src/test -p "test_*.py" -v
     ```
   - Re-deploy `src/run_robot.py` to the hubs with `.\deploy_script.ps1` before running experiments.
