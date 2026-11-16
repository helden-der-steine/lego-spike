from pybricks.hubs import PrimeHub
from pybricks.pupdevices import ColorSensor
from pybricks.parameters import Port, Button
from pybricks.tools import wait, StopWatch

hub = PrimeHub()
stopwatch = StopWatch()


def find_color_sensor():
    """Auto-detects the port where a ColorSensor is connected."""
    for port in (Port.A, Port.B, Port.E, Port.F, Port.C, Port.D):
        try:
            sensor = ColorSensor(port)
            return sensor, port
        except Exception:
            pass
    return None, None


def main():
    sensor, port = find_color_sensor()
    if sensor is None:
        print("ERROR: No ColorSensor found on ports A-F.")
        return

    print(f"ColorSensor detected on {port}")
    print("Move the robot over each of your 4 zones to inspect the readings.")
    print("Press LEFT button on the hub to stop.\n")
    print("Time_s | Color | HSV (h, s, v) | Reflection")
    print("-" * 50)

    stopwatch.reset()
    while Button.LEFT not in hub.buttons.pressed():
        t_s = round(stopwatch.time() / 1000.0, 1)
        color = sensor.color()
        hsv = sensor.hsv()
        reflection = sensor.reflection()

        print(f"{t_s:>5.1f}s | {str(color):<12} | ({int(hsv.h):3d}, {int(hsv.s):3d}, {int(hsv.v):3d}) | {int(reflection):3d}%")
        wait(500)

    print("\nStopped color sensor logging.")


if __name__ == "__main__":
    main()
