"""
Diagnostic utility for inspecting live ColorSensor HSV and reflection readings over arena zones.

Deploy to a hub with: .\\deploy_all.ps1 -ScriptPath color_sensor_logger.py -RobotIds 1
"""

from pybricks.hubs import PrimeHub
from pybricks.parameters import Button
from pybricks.tools import StopWatch, wait

from robot.hardware import find_color_sensor

SAMPLE_INTERVAL_MS = 500
TABLE_DIVIDER = "-" * 50


def main():
    hub = PrimeHub()
    stopwatch = StopWatch()

    sensor, port = find_color_sensor()
    if sensor is None:
        print("ERROR: No ColorSensor found on ports A-F.")
        return

    print(f"ColorSensor detected on {port}")
    print("Move the robot over each of your 4 zones to inspect the readings.")
    print("Press LEFT button on the hub to stop.\n")
    print("Time_s | Color | HSV (h, s, v) | Reflection")
    print(TABLE_DIVIDER)

    stopwatch.reset()
    while Button.LEFT not in hub.buttons.pressed():
        elapsed_s = round(stopwatch.time() / 1000.0, 1)
        color = sensor.color()
        hsv = sensor.hsv()
        reflection = sensor.reflection()

        print(
            f"{elapsed_s:>5.1f}s | {str(color):<12} | "
            f"({int(hsv.h):3d}, {int(hsv.s):3d}, {int(hsv.v):3d}) | {int(reflection):3d}%"
        )
        wait(SAMPLE_INTERVAL_MS)

    print("\nStopped color sensor logging.")


if __name__ == "__main__":
    main()
