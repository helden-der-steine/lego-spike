"""
Simple Log Saver for LEGO SPIKE Prime.

Extracts the JSON log dump from SPIKE App / Pybricks console output and saves
it with a timestamp inside the `logs/` folder.
"""

import json
import os
import sys
import time

from shared.sim_config import HOST_CONFIG, LOG_DUMP_END_MARKER, LOG_DUMP_START_MARKER

LOGS_DIR = HOST_CONFIG.logs_dir
TIMESTAMP_FMT = "%Y%m%d_%H%M%S"
DEFAULT_ROBOT_ID = 1


def _extract_raw_json(text: str) -> str | None:
    if LOG_DUMP_START_MARKER in text:
        after_start = text.split(LOG_DUMP_START_MARKER, 1)[1]
        return after_start.split(LOG_DUMP_END_MARKER, 1)[0].strip()
    if "[" in text and "]" in text:
        return text[text.find("[") : text.rfind("]") + 1]
    return None


def save_json_log(text: str, output_dir: str = LOGS_DIR) -> str | None:
    """Parses a JSON log array from `text` and writes it to `output_dir`."""
    raw = _extract_raw_json(text)
    if raw is None:
        print("Error: Could not find JSON log data in the text.")
        return None

    data = json.loads(raw)
    robot_id = data[0].get("ID", DEFAULT_ROBOT_ID) if data else DEFAULT_ROBOT_ID
    timestamp = time.strftime(TIMESTAMP_FMT)

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"log_robot_{robot_id}_{timestamp}.json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved {len(data)} entries to: {filepath}")
    return filepath


def main() -> None:
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            save_json_log(f.read())
    else:
        print("Paste the SPIKE App console output below, then press Ctrl+D (or Ctrl+Z on Windows):")
        save_json_log(sys.stdin.read())


if __name__ == "__main__":
    main()
