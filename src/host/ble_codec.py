"""
Pybricks BLE Broadcast/Observe payload encoder and decoder.

Implements the Pybricks Manufacturer Specific Data format (Company ID 0x0397):
- Byte 0: channel number (0..255)
- Remaining bytes: sequence of typed values, each prefixed by a 1-byte header
  where bits 7..5 encode the value type and bits 4..0 encode the byte length.
"""

from enum import IntEnum
import struct

MAX_CHANNEL = 255
MAX_PAYLOAD_BYTES = 26
MAX_VARLEN_BYTES = 31

TYPE_SHIFT = 5
LENGTH_MASK = 0x1F


class PybricksValueType(IntEnum):
    """Pybricks BLE payload value type tags (3-bit header prefix)."""

    SINGLE_OBJECT = 0
    TRUE = 1
    FALSE = 2
    INT = 3
    FLOAT = 4
    STR = 5
    BYTES = 6


SINGLE_OBJECT_HEADER = (PybricksValueType.SINGLE_OBJECT << TYPE_SHIFT) | 0

INT8_MIN, INT8_MAX = -128, 127
INT16_MIN, INT16_MAX = -32768, 32767
FLOAT_ROUND_DIGITS = 2


def _make_header(val_type: PybricksValueType, length: int) -> int:
    return (val_type << TYPE_SHIFT) | length


def _encode_single_value(val) -> bytes:
    """Encodes a single Python scalar value using the Pybricks BLE header format."""
    if val is True:
        return bytes([_make_header(PybricksValueType.TRUE, 0)])
    if val is False:
        return bytes([_make_header(PybricksValueType.FALSE, 0)])
    if isinstance(val, int):
        if INT8_MIN <= val <= INT8_MAX:
            return bytes([_make_header(PybricksValueType.INT, 1)]) + struct.pack("<b", val)
        if INT16_MIN <= val <= INT16_MAX:
            return bytes([_make_header(PybricksValueType.INT, 2)]) + struct.pack("<h", val)
        return bytes([_make_header(PybricksValueType.INT, 4)]) + struct.pack("<i", val)
    if isinstance(val, float):
        return bytes([_make_header(PybricksValueType.FLOAT, 4)]) + struct.pack("<f", val)
    if isinstance(val, str):
        raw = val.encode("utf-8")[:MAX_VARLEN_BYTES]
        return bytes([_make_header(PybricksValueType.STR, len(raw))]) + raw
    if isinstance(val, (bytes, bytearray)):
        raw = bytes(val)[:MAX_VARLEN_BYTES]
        return bytes([_make_header(PybricksValueType.BYTES, len(raw))]) + raw
    raise TypeError(f"Unsupported Pybricks broadcast type: {type(val)}")


def encode_pybricks_payload(channel: int, data) -> bytes:
    """
    Encodes a channel (0..255) and scalar/sequence into raw Manufacturer Data bytes.
    """
    if not (0 <= channel <= MAX_CHANNEL):
        raise ValueError(f"Channel must be between 0 and {MAX_CHANNEL}")

    out = bytearray([channel])
    if isinstance(data, (tuple, list)):
        for item in data:
            out.extend(_encode_single_value(item))
    else:
        out.append(SINGLE_OBJECT_HEADER)
        out.extend(_encode_single_value(data))

    if len(out) > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"Encoded Pybricks broadcast payload exceeds {MAX_PAYLOAD_BYTES} bytes ({len(out)} bytes)"
        )
    return bytes(out)


def _decode_int(raw_val: bytes, length: int) -> int:
    if length == 1:
        return struct.unpack("<b", raw_val)[0]
    if length == 2:
        return struct.unpack("<h", raw_val)[0]
    if length == 4:
        return struct.unpack("<i", raw_val)[0]
    return int.from_bytes(raw_val, "little", signed=True)


def decode_pybricks_payload(data: bytes) -> tuple[int, list] | None:
    """
    Decodes a Pybricks Manufacturer Specific Data payload.

    Returns `(channel, list_of_decoded_values)` or None if `data` is empty.
    """
    if not data:
        return None

    channel = data[0]
    index = 1
    values = []

    while index < len(data):
        header = data[index]
        index += 1

        val_type = header >> TYPE_SHIFT
        length = header & LENGTH_MASK

        if index + length > len(data):
            break

        raw_val = data[index : index + length]
        index += length

        if val_type == PybricksValueType.SINGLE_OBJECT:
            continue
        if val_type == PybricksValueType.TRUE:
            values.append(True)
        elif val_type == PybricksValueType.FALSE:
            values.append(False)
        elif val_type == PybricksValueType.INT:
            values.append(_decode_int(raw_val, length))
        elif val_type == PybricksValueType.FLOAT:
            if length == 4:
                values.append(round(struct.unpack("<f", raw_val)[0], FLOAT_ROUND_DIGITS))
        elif val_type == PybricksValueType.STR:
            try:
                values.append(raw_val.decode("utf-8"))
            except UnicodeDecodeError:
                values.append(str(raw_val))
        elif val_type == PybricksValueType.BYTES:
            values.append(raw_val)

    return channel, values
