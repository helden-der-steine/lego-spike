"""
Connectionless BLE broadcaster for Windows using WinRT BluetoothLEAdvertisementPublisher.
"""

import asyncio
import sys

from host.ble_codec import encode_pybricks_payload
from shared.protocol import CONTROL_CHANNEL, LEGO_COMPANY_ID

DEFAULT_BROADCAST_DURATION_S = 1.8
WINDOWS_PLATFORM = "win32"


def _create_winrt_publisher(payload: bytes):
    """
    Creates a Windows BluetoothLEAdvertisementPublisher configured with
    LEGO Company ID (0x0397) and the given Pybricks payload bytes.
    Supports both `winrt` (installed with bleak) and legacy `winsdk`.
    """
    try:
        from winrt.windows.devices.bluetooth.advertisement import (
            BluetoothLEAdvertisementPublisher,
            BluetoothLEManufacturerData,
        )
        from winrt.windows.storage.streams import Buffer, DataWriter

        try:
            buf = Buffer(len(payload))
            buf.length = buf.capacity
            with memoryview(buf) as mv:
                mv[:] = payload
        except Exception:
            writer = DataWriter()
            writer.write_bytes(payload)
            buf = writer.detach_buffer()

        mfg = BluetoothLEManufacturerData(LEGO_COMPANY_ID, buf)
        pub = BluetoothLEAdvertisementPublisher()
        pub.advertisement.manufacturer_data.append(mfg)
        return pub
    except ImportError:
        from winsdk.windows.devices.bluetooth.advertisement import (
            BluetoothLEAdvertisementPublisher,
            BluetoothLEManufacturerData,
        )
        from winsdk.windows.storage.streams import DataWriter

        writer = DataWriter()
        writer.write_bytes(list(payload))
        buf = writer.detach_buffer()

        mfg = BluetoothLEManufacturerData()
        mfg.company_id = LEGO_COMPANY_ID
        mfg.data = buf

        pub = BluetoothLEAdvertisementPublisher()
        pub.advertisement.manufacturer_data.append(mfg)
        return pub


class ChannelZeroBroadcaster:
    """Broadcasts connectionless Pybricks control commands on BLE Channel 0."""

    def __init__(self, channel: int = CONTROL_CHANNEL):
        self.channel = channel
        self._publisher = None

    def stop(self) -> None:
        """Stops any active BLE advertisement publisher."""
        if self._publisher is not None:
            try:
                self._publisher.stop()
            except Exception:
                pass
            self._publisher = None

    async def broadcast_command(
        self, value, duration_s: float = DEFAULT_BROADCAST_DURATION_S
    ) -> bool:
        """
        Broadcasts `value` on `self.channel` for `duration_s` seconds, then stops.
        Returns True if transmitted over BLE hardware, False on unsupported OS or error.
        """
        self.stop()
        payload = encode_pybricks_payload(self.channel, value)

        if sys.platform != WINDOWS_PLATFORM:
            print(
                f"⚠️ [OS Notice] Raw BLE Manufacturer Data advertising requires Windows (current OS: {sys.platform}).\n"
                f"   Encoded Channel {self.channel} payload: {payload.hex()}"
            )
            return False

        try:
            pub = _create_winrt_publisher(payload)
            pub.start()
            self._publisher = pub
            await asyncio.sleep(duration_s)
            return True
        except Exception as exc:
            print(f"❌ Failed to broadcast on BLE Channel {self.channel}: {type(exc).__name__}: {exc}")
            return False
        finally:
            self.stop()
