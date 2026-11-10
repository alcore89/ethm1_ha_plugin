"""Minimal asynchronous SATEL INTEGRA / legacy ETHM-1 protocol client.

Implements the SATEL integration protocol used on the ETHM-1 integration port
(normally TCP/7094), including the optional native AES-192 integration encryption.
It intentionally covers only what this Home Assistant integration needs: panel
info, discovery of zones/partitions, live state polling, and arm/disarm commands.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

FRAME_START = b"\xFE\xFE"
FRAME_END = b"\xFE\x0D"
CMD_RESULT = 0xEF
CMD_READ_DEVICE = 0xEE
CMD_PANEL_INFO = 0x7E
CMD_ETHM_VERSION = 0x7C

# State commands (the command number is also the state type number).
CMD_ZONE_VIOLATION = 0x00
CMD_ARMED_PARTITION = 0x0A
CMD_ARMED_MODE_2 = 0x0B
CMD_ARMED_MODE_3 = 0x0C
CMD_PARTITION_ENTRY_TIME = 0x0E
CMD_PARTITION_EXIT_OVER_10 = 0x0F
CMD_PARTITION_EXIT_UNDER_10 = 0x10
CMD_PARTITION_ALARM = 0x13

# Control commands.
CMD_ARM_FULL = 0x80
CMD_ARM_MODE_1 = 0x81
CMD_ARM_MODE_2 = 0x82
CMD_ARM_MODE_3 = 0x83
CMD_DISARM = 0x84
CMD_CLEAR_ALARM = 0x85

RESULT_OK = 0x00
RESULT_OTHER_ERROR = 0x08
RESULT_CANNOT_ARM_FORCE = 0x11
RESULT_CANNOT_ARM = 0x12
RESULT_ACCEPTED = 0xFF

RESULT_TEXT = {
    0x00: "OK",
    0x01: "user code not found",
    0x02: "no access",
    0x03: "selected user does not exist",
    0x04: "selected user already exists",
    0x05: "wrong or duplicate code",
    0x06: "telephone code exists",
    0x07: "changed code is the same",
    0x08: "other error",
    0x11: "cannot arm, force arm may be possible",
    0x12: "cannot arm",
    0xFF: "command accepted",
}

PANEL_MODELS = {
    0x00: ("INTEGRA 24", 24),
    0x01: ("INTEGRA 32", 32),
    0x02: ("INTEGRA 64", 64),
    0x03: ("INTEGRA 128", 128),
    0x04: ("INTEGRA 128-WRL SIM300", 128),
    0x84: ("INTEGRA 128-WRL LEON", 128),
    0x42: ("INTEGRA 64 Plus", 64),
    0x43: ("INTEGRA 128 Plus", 128),
    0x48: ("INTEGRA 256 Plus", 256),
}

# SATEL language IDs. Polish and other Central European languages use CP1250.
CP1250_LANGUAGES = {0, 5, 7}  # Polish, Slovak, Czech
CP1252_LANGUAGES = {4, 15, 16}  # German, French, Spanish


class SatelError(Exception):
    """Base SATEL protocol error."""


class SatelConnectionError(SatelError):
    """Connection or transport error."""


class SatelProtocolError(SatelError):
    """Malformed or unexpected protocol response."""


class SatelCommandError(SatelError):
    """Command rejected by the alarm panel."""

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(RESULT_TEXT.get(status, f"SATEL error 0x{status:02X}"))


@dataclass(frozen=True)
class PanelInfo:
    """Basic panel information."""

    model_id: int
    model: str
    capacity: int
    version: str
    language: int


@dataclass(frozen=True)
class ZoneInfo:
    """Configured alarm zone."""

    zone_id: int
    name: str
    function: int
    partition_id: int


@dataclass(frozen=True)
class PartitionInfo:
    """Configured alarm partition."""

    partition_id: int
    name: str
    function: int


@dataclass(frozen=True)
class SatelStatus:
    """Polled state snapshot."""

    violated_zones: frozenset[int]
    armed_partitions: frozenset[int]
    mode2_partitions: frozenset[int]
    mode3_partitions: frozenset[int]
    entry_time_partitions: frozenset[int]
    exit_time_partitions: frozenset[int]
    alarm_partitions: frozenset[int]


def _crc(data: bytes) -> int:
    crc = 0x147A
    for byte in data:
        crc = ((crc << 1) & 0xFFFF) | ((crc >> 15) & 0x01)
        crc ^= 0xFFFF
        crc = (crc + ((crc >> 8) & 0xFF) + byte) & 0xFFFF
    return crc


def _escape(data: bytes) -> bytes:
    out = bytearray()
    for byte in data:
        if byte == 0xFE:
            out.extend(b"\xFE\xF0")
        else:
            out.append(byte)
    return bytes(out)


def _unescape(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0xFE and i + 1 < len(data) and data[i + 1] == 0xF0:
            out.append(0xFE)
            i += 2
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


def _frame(command: int, data: bytes = b"") -> bytes:
    payload = bytes([command]) + data
    crc = _crc(payload)
    body = payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
    return FRAME_START + _escape(body) + FRAME_END




def _derive_aes_key(integration_key: str) -> bytes:
    """Convert SATEL integration key (max 12 ASCII chars) to AES-192 key."""
    try:
        raw = integration_key.encode("ascii")
    except UnicodeEncodeError as err:
        raise ValueError("Integration key must contain ASCII characters only") from err
    if len(raw) > 12:
        raise ValueError("Integration key must be at most 12 ASCII characters")
    half = raw.ljust(12, b" ")
    return half + half


class _SatelAesCipher:
    """SATEL AES-192 transform used by encrypted ETHM integration."""

    def __init__(self, integration_key: str) -> None:
        key = _derive_aes_key(integration_key)
        self._cipher = Cipher(algorithms.AES(key), modes.ECB())

    def _encrypt_block(self, block: bytes) -> bytes:
        encryptor = self._cipher.encryptor()
        return encryptor.update(block) + encryptor.finalize()

    def _decrypt_block(self, block: bytes) -> bytes:
        decryptor = self._cipher.decryptor()
        return decryptor.update(block) + decryptor.finalize()

    def encrypt(self, buffer: bytes) -> bytes:
        if not buffer:
            return b""
        work = bytearray(buffer)
        cv = bytearray(self._encrypt_block(bytes(16)))
        index = 0
        count = len(work)

        while count > 0:
            if count > 15:
                block = bytearray(work[index : index + 16])
                for i in range(16):
                    block[i] ^= cv[i]
                encrypted = self._encrypt_block(bytes(block))
                cv[:] = encrypted
                work[index : index + 16] = encrypted
                index += 16
                count -= 16
            else:
                cv[:] = self._encrypt_block(bytes(cv))
                for i in range(count):
                    work[index + i] ^= cv[i]
                count = 0

        return bytes(work)

    def decrypt(self, buffer: bytes) -> bytes:
        if not buffer:
            return b""
        work = bytearray(buffer)
        cv = bytearray(self._encrypt_block(bytes(16)))
        index = 0
        count = len(work)

        while count > 0:
            if count > 15:
                encrypted_block = bytes(work[index : index + 16])
                plain = bytearray(self._decrypt_block(encrypted_block))
                for i in range(16):
                    plain[i] ^= cv[i]
                cv[:] = encrypted_block
                work[index : index + 16] = plain
                index += 16
                count -= 16
            else:
                cv[:] = self._encrypt_block(bytes(cv))
                for i in range(count):
                    work[index + i] ^= cv[i]
                count = 0

        return bytes(work)


def _decode_name(raw: bytes, language: int) -> str:
    if language in CP1250_LANGUAGES:
        encoding = "cp1250"
    elif language in CP1252_LANGUAGES:
        encoding = "cp1252"
    else:
        encoding = "utf-8"
    try:
        return raw.decode(encoding).strip(" \x00")
    except UnicodeDecodeError:
        return raw.decode("cp1250", errors="replace").strip(" \x00")


def _active_bits(data: bytes) -> frozenset[int]:
    result: set[int] = set()
    for byte_no, value in enumerate(data):
        for bit in range(8):
            if value & (1 << bit):
                result.add(byte_no * 8 + bit + 1)
    return frozenset(result)


def _encode_user_code(code: str) -> bytes:
    code = code.strip()
    if not code.isdigit() or not 1 <= len(code) <= 16:
        raise ValueError("User code must contain 1-16 digits")

    digits = [int(char) for char in code]
    if len(digits) % 2:
        digits.append(0x0F)

    result = bytearray()
    for i in range(0, len(digits), 2):
        result.append((digits[i] << 4) | digits[i + 1])
    while len(result) < 8:
        result.append(0xFF)
    return bytes(result[:8])


def _partition_bitmap(partition_id: int) -> bytes:
    if not 1 <= partition_id <= 32:
        raise ValueError("Partition ID must be 1-32")
    data = bytearray(4)
    index = partition_id - 1
    data[index // 8] |= 1 << (index % 8)
    return bytes(data)


class SatelClient:
    """Async request/response client for a legacy ETHM-1."""

    def __init__(
        self,
        host: str,
        port: int,
        user_code: str,
        integration_key: str = "",
        timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.user_code = user_code
        self.integration_key = integration_key
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self.panel_info: PanelInfo | None = None
        self._cipher = _SatelAesCipher(integration_key) if integration_key else None
        self._id_r = 0
        self._rolling_counter = 0

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    @property
    def encrypted(self) -> bool:
        return self._cipher is not None

    async def connect(self) -> None:
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
            self._id_r = 0
            self._rolling_counter = 0
        except (OSError, asyncio.TimeoutError) as err:
            await self.close()
            raise SatelConnectionError(
                f"Cannot connect to {self.host}:{self.port}: {err}"
            ) from err

    async def close(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        self._id_r = 0
        self._rolling_counter = 0
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ConnectionError):
                pass

    def _wrap_encrypted(self, plain_frame: bytes) -> bytes:
        if self._cipher is None:
            return plain_frame

        bytes_count = max(16, 6 + len(plain_frame))
        if bytes_count > 255:
            raise SatelProtocolError("Encrypted SATEL packet is too large")

        data = bytearray(bytes_count)
        rnd = secrets.randbits(16)
        data[0] = (rnd >> 8) & 0xFF
        data[1] = rnd & 0xFF
        data[2] = (self._rolling_counter >> 8) & 0xFF
        data[3] = self._rolling_counter & 0xFF
        data[4] = secrets.randbits(8)
        data[5] = self._id_r
        self._rolling_counter = (self._rolling_counter + 1) & 0xFFFF
        data[6 : 6 + len(plain_frame)] = plain_frame

        encrypted = self._cipher.encrypt(bytes(data))
        return bytes([bytes_count]) + encrypted

    async def _read_plain_frame(self) -> tuple[int, bytes]:
        if self._reader is None:
            raise SatelConnectionError("Not connected")
        try:
            raw = await asyncio.wait_for(
                self._reader.readuntil(FRAME_END), timeout=self.timeout
            )
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError) as err:
            raise SatelConnectionError(f"Read failed: {err}") from err

        start = raw.find(FRAME_START)
        if start < 0 or not raw.endswith(FRAME_END):
            raise SatelProtocolError(f"Invalid frame: {raw.hex()}")

        body = _unescape(raw[start + 2 : -2])
        if len(body) < 3:
            raise SatelProtocolError("Frame is too short")

        payload = body[:-2]
        received_crc = (body[-2] << 8) | body[-1]
        calculated_crc = _crc(payload)
        if received_crc != calculated_crc:
            raise SatelProtocolError(
                f"CRC mismatch RX={received_crc:04X} CALC={calculated_crc:04X}"
            )
        return payload[0], payload[1:]

    async def _read_encrypted_frame(self) -> tuple[int, bytes]:
        if self._reader is None or self._cipher is None:
            raise SatelConnectionError("Encrypted transport is not initialized")
        try:
            length_raw = await asyncio.wait_for(
                self._reader.readexactly(1), timeout=self.timeout
            )
            length = length_raw[0]
            if length < 16:
                raise SatelProtocolError(
                    f"Invalid encrypted payload length: {length}"
                )
            encrypted = await asyncio.wait_for(
                self._reader.readexactly(length), timeout=self.timeout
            )
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError) as err:
            raise SatelConnectionError(f"Encrypted read failed: {err}") from err

        payload = self._cipher.decrypt(encrypted)
        if len(payload) < 6:
            raise SatelProtocolError("Encrypted payload is too short")

        self._id_r = payload[4]
        raw = payload[6:]
        start = raw.find(FRAME_START)
        if start < 0:
            raise SatelProtocolError("Missing SATEL frame in encrypted payload")
        end = raw.find(FRAME_END, start + 2)
        if end < 0:
            raise SatelProtocolError("Missing encrypted SATEL frame terminator")
        body = _unescape(raw[start + 2 : end])
        if len(body) < 3:
            raise SatelProtocolError("Encrypted SATEL frame is too short")
        inner = body[:-2]
        received_crc = (body[-2] << 8) | body[-1]
        calculated_crc = _crc(inner)
        if received_crc != calculated_crc:
            raise SatelProtocolError(
                f"CRC mismatch RX={received_crc:04X} CALC={calculated_crc:04X}"
            )
        return inner[0], inner[1:]

    async def request(self, command: int, data: bytes = b"") -> tuple[int, bytes]:
        async with self._lock:
            await self.connect()
            assert self._writer is not None
            try:
                plain = _frame(command, data)
                wire = self._wrap_encrypted(plain)
                if command >= 0x80:
                    _LOGGER.debug("SATEL TX %02X: <control payload redacted>", command)
                else:
                    _LOGGER.debug(
                        "SATEL TX %02X (%s): %s",
                        command,
                        "encrypted" if self.encrypted else "clear",
                        plain.hex(" "),
                    )
                self._writer.write(wire)
                await self._writer.drain()
                response_command, response_data = (
                    await self._read_encrypted_frame()
                    if self.encrypted
                    else await self._read_plain_frame()
                )
                _LOGGER.debug(
                    "SATEL RX %02X: %s", response_command, response_data.hex(" ")
                )
            except (OSError, ConnectionError, SatelConnectionError, SatelProtocolError):
                await self.close()
                raise

            if response_command not in (command, CMD_RESULT):
                await self.close()
                raise SatelProtocolError(
                    f"Unexpected response 0x{response_command:02X} for 0x{command:02X}"
                )
            return response_command, response_data

    async def get_panel_info(self) -> PanelInfo:
        response_command, data = await self.request(CMD_PANEL_INFO)
        if response_command == CMD_RESULT:
            status = data[0] if data else 0xFF
            raise SatelCommandError(status)
        if len(data) != 14:
            raise SatelProtocolError(f"Unexpected panel info length: {len(data)}")

        model_id = data[0]
        model, capacity = PANEL_MODELS.get(model_id, (f"INTEGRA 0x{model_id:02X}", 128))
        version_raw = data[1:12].decode("ascii", errors="replace")
        if len(version_raw) == 11:
            version = (
                f"{version_raw[0]}.{version_raw[1:3]} "
                f"{version_raw[3:7]}-{version_raw[7:9]}-{version_raw[9:11]}"
            )
        else:
            version = version_raw
        language = data[12]
        self.panel_info = PanelInfo(model_id, model, capacity, version, language)
        return self.panel_info

    async def get_ethm_version(self) -> str:
        response_command, data = await self.request(CMD_ETHM_VERSION)
        if response_command == CMD_RESULT:
            status = data[0] if data else 0xFF
            raise SatelCommandError(status)
        return data[:11].decode("ascii", errors="replace")

    async def discover_zones(self) -> list[ZoneInfo]:
        if self.panel_info is None:
            await self.get_panel_info()
        assert self.panel_info is not None

        zones: list[ZoneInfo] = []
        for zone_id in range(1, self.panel_info.capacity + 1):
            # Newer protocol revision: type 0x05 includes partition assignment.
            response_command, data = await self.request(
                CMD_READ_DEVICE, bytes([0x05, zone_id & 0xFF])
            )
            if response_command == CMD_READ_DEVICE:
                # type, id, function, 16-byte name, partition
                if len(data) != 20 or data[0] != 0x05:
                    raise SatelProtocolError(
                        f"Unexpected zone {zone_id} response: {data.hex()}"
                    )
                actual_id = data[1]
                function = data[2]
                name = _decode_name(data[3:-1], self.panel_info.language)
                partition_id = data[-1]
                zones.append(
                    ZoneInfo(
                        zone_id=actual_id,
                        name=name or f"Zone {actual_id}",
                        function=function,
                        partition_id=partition_id,
                    )
                )
                continue

            status = data[0] if data else 0xFF
            if status != RESULT_OTHER_ERROR:
                raise SatelCommandError(status)

            # Compatibility fallback used by older protocol revisions: type 0x01
            # returns zone number/function/name, but not its partition assignment.
            response_command, data = await self.request(
                CMD_READ_DEVICE, bytes([0x01, zone_id & 0xFF])
            )
            if response_command == CMD_RESULT:
                status = data[0] if data else 0xFF
                if status == RESULT_OTHER_ERROR:
                    continue
                raise SatelCommandError(status)

            if len(data) != 19 or data[0] != 0x01:
                raise SatelProtocolError(
                    f"Unexpected legacy zone {zone_id} response: {data.hex()}"
                )
            actual_id = data[1]
            function = data[2]
            name = _decode_name(data[3:], self.panel_info.language)
            zones.append(
                ZoneInfo(
                    zone_id=actual_id,
                    name=name or f"Zone {actual_id}",
                    function=function,
                    partition_id=0,
                )
            )
        return zones

    async def get_partition(self, partition_id: int) -> PartitionInfo | None:
        if self.panel_info is None:
            await self.get_panel_info()
        assert self.panel_info is not None

        response_command, data = await self.request(
            CMD_READ_DEVICE, bytes([0x00, partition_id & 0xFF])
        )
        if response_command == CMD_RESULT:
            status = data[0] if data else 0xFF
            if status == RESULT_OTHER_ERROR:
                return None
            raise SatelCommandError(status)

        # type, id, function, 16-byte name
        if len(data) != 19 or data[0] != 0x00:
            raise SatelProtocolError(
                f"Unexpected partition {partition_id} response: {data.hex()}"
            )
        actual_id = data[1]
        function = data[2]
        name = _decode_name(data[3:], self.panel_info.language)
        return PartitionInfo(
            partition_id=actual_id,
            name=name or f"Partition {actual_id}",
            function=function,
        )

    async def discover_partitions_for_zones(
        self, zones: list[ZoneInfo]
    ) -> list[PartitionInfo]:
        known_ids = {z.partition_id for z in zones if 1 <= z.partition_id <= 32}
        # If the panel only supports the older zone-information record (0x01),
        # partition assignment is not included. In that case scan all 32 slots.
        if zones and any(z.partition_id == 0 for z in zones):
            partition_ids = range(1, 33)
        else:
            partition_ids = sorted(known_ids)

        partitions: list[PartitionInfo] = []
        for partition_id in partition_ids:
            partition = await self.get_partition(partition_id)
            if partition is not None:
                partitions.append(partition)
        return partitions

    async def _read_bits(self, command: int) -> frozenset[int]:
        response_command, data = await self.request(command)
        if response_command == CMD_RESULT:
            status = data[0] if data else 0xFF
            raise SatelCommandError(status)
        return _active_bits(data)

    async def read_status(self) -> SatelStatus:
        # Sequential by design: the old ETHM request/response stream should not be multiplexed.
        violated = await self._read_bits(CMD_ZONE_VIOLATION)
        armed = await self._read_bits(CMD_ARMED_PARTITION)
        mode2 = await self._read_bits(CMD_ARMED_MODE_2)
        mode3 = await self._read_bits(CMD_ARMED_MODE_3)
        entry = await self._read_bits(CMD_PARTITION_ENTRY_TIME)
        exit_over = await self._read_bits(CMD_PARTITION_EXIT_OVER_10)
        exit_under = await self._read_bits(CMD_PARTITION_EXIT_UNDER_10)
        alarms = await self._read_bits(CMD_PARTITION_ALARM)
        return SatelStatus(
            violated_zones=violated,
            armed_partitions=armed,
            mode2_partitions=mode2,
            mode3_partitions=mode3,
            entry_time_partitions=entry,
            exit_time_partitions=frozenset(set(exit_over) | set(exit_under)),
            alarm_partitions=alarms,
        )

    async def _control(self, command: int, partition_id: int) -> None:
        payload = _encode_user_code(self.user_code) + _partition_bitmap(partition_id)
        response_command, data = await self.request(command, payload)
        if response_command != CMD_RESULT or not data:
            raise SatelProtocolError(
                f"Unexpected control response for 0x{command:02X}"
            )
        status = data[0]
        if status not in (RESULT_OK, RESULT_ACCEPTED):
            raise SatelCommandError(status)

    async def arm_away(self, partition_id: int) -> None:
        await self._control(CMD_ARM_FULL, partition_id)

    async def arm_home(self, partition_id: int) -> None:
        # SATEL mode 2: armed without internal zones.
        await self._control(CMD_ARM_MODE_2, partition_id)

    async def arm_night(self, partition_id: int) -> None:
        # SATEL mode 3: armed without internal zones and without entry delay.
        await self._control(CMD_ARM_MODE_3, partition_id)

    async def disarm(self, partition_id: int) -> None:
        await self._control(CMD_DISARM, partition_id)

    async def clear_alarm(self, partition_id: int) -> None:
        await self._control(CMD_CLEAR_ALARM, partition_id)
