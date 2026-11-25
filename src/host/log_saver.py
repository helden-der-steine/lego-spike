"""
Simple Log Saver for LEGO SPIKE Prime.

Extracts the JSON log dump from SPIKE App / Pybricks console output and saves
it with a timestamp inside the `logs/` folder.
"""

import json
from pathlib import Path
import sys
import time

from shared.sim_config import HOST_CONFIG, LOG_DUMP_END_MARKER, LOG_DUMP_START_MARKER

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = PROJECT_ROOT / HOST_CONFIG.logs_dir
TIMESTAMP_FMT = "%Y%m%d_%H%M%S"
DEFAULT_ROBOT_ID = 1


def _extract_raw_json(text: str) -> str | None:
    if LOG_DUMP_START_MARKER in text:
        after_start = text.split(LOG_DUMP_START_MARKER, 1)[1]
        return after_start.split(LOG_DUMP_END_MARKER, 1)[0].strip()
    if "[" in text and "]" in text:
        return text[text.find("[") : text.rfind("]") + 1]
    return None


def save_json_log(text: str, output_dir: str | Path = LOGS_DIR) -> Path | None:
    """Parses a JSON log array from `text` and writes it to `output_dir`."""
    raw = _extract_raw_json(text)
    if raw is None:
        print("Error: Could not find JSON log data in the text.")
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON log data: {exc}")
        return None

    if not isinstance(data, list):
        print("Error: Expected a JSON array of log entries.")
        return None

    first_row = data[0] if data and isinstance(data[0], dict) else {}
    robot_id = first_row.get("ID", DEFAULT_ROBOT_ID)
    timestamp = time.strftime(TIMESTAMP_FMT)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / f"log_robot_{robot_id}_{timestamp}.json"

    with filepath.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved {len(data)} entries to: {filepath}")
    return filepath


def main() -> None:
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if input_path.is_file():
            save_json_log(input_path.read_text(encoding="utf-8"))
            return
    print("Paste the SPIKE App console output below, then press Ctrl+D (or Ctrl+Z on Windows):")
    save_json_log(sys.stdin.read())


if __name__ == "__main__":
    main()
