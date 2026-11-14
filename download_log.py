#!/usr/bin/env python3
"""
Simple Log Saver for LEGO SPIKE Prime
Paste the console output from the SPIKE App, press Ctrl+D, and it saves the JSON log with a timestamp inside the 'logs/' folder.
"""

import os
import sys
import json
import time

def save_json_log(text):
    # Extract JSON between markers or raw JSON array
    if "=== JSON LOG DUMP START ===" in text:
        raw = text.split("=== JSON LOG DUMP START ===")[1].split("=== JSON LOG DUMP END ===")[0].strip()
    elif "[" in text and "]" in text:
        raw = text[text.find("["):text.rfind("]") + 1]
    else:
        print("Error: Could not find JSON log data in the text.")
        return None

    data = json.loads(raw)
    robot_id = data[0].get("ID", 1) if data else 1
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Save in 'logs/' folder with timestamp in filename
    os.makedirs("logs", exist_ok=True)
    filepath = os.path.join("logs", f"log_robot_{robot_id}_{timestamp}.json")

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved {len(data)} entries to: {filepath}")
    return filepath

if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], "r") as f:
            save_json_log(f.read())
    else:
        print("Paste the SPIKE App console output below, then press Ctrl+D (or Ctrl+Z on Windows):")
        save_json_log(sys.stdin.read())
