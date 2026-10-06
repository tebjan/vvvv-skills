"""VL's exact 22-character GUID encoding.

Keep this compatible with VL.Model.Internal.GUIDEncoders in
vvvv50/VL.Lang/src/ImmutableModel/Internal/GUIDEncoders.cs. VL encodes the
two big-endian 64-bit chunks of Guid.ToByteArray() separately; encoding the
UUID as one 128-bit integer with an ordinary base62 alphabet is not VL's
format, even though it also produces 22 printable characters.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
ID_LENGTH = 22
ID_PATTERN = re.compile(r"^[0-9A-Za-z]{22}$")


def guid_to_vl_id(guid: UUID) -> str:
    """Match GUIDEncoders.GuidTobase62(Guid) including .NET GUID byte order."""

    data = guid.bytes_le  # Guid.ToByteArray() uses little-endian fields 0-2.
    result: list[str] = []
    for offset in (0, 8):
        value = int.from_bytes(data[offset:offset + 8], "big")
        digits = [ALPHABET[0]] * 11
        for index in range(10, -1, -1):
            value, remainder = divmod(value, 62)
            digits[index] = ALPHABET[remainder]
        result.extend(digits)
    return "".join(result)


def new_vl_id() -> str:
    """Return a GUID ID encoded exactly as vvvv gamma serializes it."""

    return guid_to_vl_id(uuid4())
