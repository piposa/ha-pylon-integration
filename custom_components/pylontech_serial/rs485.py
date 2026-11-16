"""Read-only Pylontech low-voltage RS485 protocol."""
import re
from datetime import datetime
from time import monotonic, sleep

_FRAME = re.compile(rb"~([0-9A-Fa-f]+)\r$")
_ALARMS = {0: "normal", 1: "below lower limit", 2: "above higher limit", 0xF0: "other error"}
_DYNAMIC = (0x42, 0x44, 0x92)
_STATIC = (0x93, 0x51, 0x4F, 0x96, 0x47)
_DISCOVERY_TIMEOUT = 0.4
_NO_RESPONSE = (EOFError, TimeoutError, ValueError)
_COMMAND_DELAY = 0.1  # Minimum inter-command delay supported by PylonLowVoltage.


def request_frame(address, command):
    """Encode a read request, including the length and ASCII checksums."""
    version = 0 if command == 0x4F else 0x20
    info = "" if command in (0x4F, 0x51) else f"{address:02X}"
    length = len(info)
    body = f"{version:02X}{address:02X}46{command:02X}{(-length & 0xF):X}{length:03X}{info}".encode()
    return b"~" + body + f"{-sum(body) & 0xFFFF:04X}\r".encode()


def response_payload(frame, address):
    """Validate a complete response and return its version and data."""
    match = _FRAME.search(frame)
    if not match or len(match[1]) < 16 or len(match[1]) % 2:
        raise ValueError("Invalid RS485 frame")
    body, checksum = match[1][:-4], match[1][-4:]
    if int(checksum, 16) != (-sum(body) & 0xFFFF):
        raise ValueError("Invalid RS485 checksum")
    version, source, kind, status = bytes.fromhex(body[:8].decode())
    if source != address or kind != 0x46:
        raise ValueError(f"Unexpected RS485 response address or type ({source:02X}/{kind:02X})")
    if status:
        raise ValueError(f"BMS returned status {status:02X}")
    length = int(body[9:12], 16)
    length_sum = sum(int(bytes([digit]), 16) for digit in body[9:12])
    if len(body[12:]) != length or int(body[8:9], 16) != (-length_sum & 0xF):
        raise ValueError("Invalid RS485 data length")
    return version, bytes.fromhex(body[12:].decode())


class Payload:
    """Read fields from a bounded payload in order."""

    def __init__(self, data):
        self.data = data
        self.offset = 0

    def take(self, count):
        end = self.offset + count
        if end > len(self.data):
            raise ValueError("Truncated RS485 payload")
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def integer(self, count=1, *, signed=False):
        return int.from_bytes(self.take(count), "big", signed=signed)

    def vector(self, width):
        return [self.integer(width) for _ in range(self.integer())]


def _analog(data):
    cells = [value / 1000 for value in data.vector(2)]
    temperatures = [(value - 2731) / 10 for value in data.vector(2)]
    if not cells:
        raise ValueError("BMS reported zero cells")
    current = data.integer(2, signed=True) / 10
    voltage = data.integer(2) / 1000
    remaining = data.integer(2) / 1000
    capacity_format = data.integer()
    capacity = data.integer(2) / 1000
    cycles = data.integer(2)
    if capacity_format == 4:
        remaining = data.integer(3) / 1000
        capacity = data.integer(3) / 1000
    elif capacity_format != 2:
        raise ValueError(f"Unsupported BMS capacity format {capacity_format}")
    average = voltage / len(cells)
    readings = {
        "packVolt": voltage,
        "packCurrent": current,
        "packPower": round(voltage * current, 2),
        "packCapacity": capacity,
        "packCapacityRemain": remaining,
        "packSOC": round(remaining / capacity * 100, 2) if capacity else None,
        "packCycles": cycles,
        "packCellcount": len(cells),
        "numberTempPos": len(temperatures),
        "packState": "charging" if current > 0 else "discharging" if current < 0 else "idle",
        "cellVoltageAvg": round(average, 5),
        "cellVoltageMin": min(cells),
        "cellVoltageMax": max(cells),
        "packImbalance": round((max(cells) - min(cells)) / average * 100, 3) if average else None,
    }
    readings.update({f"cellVoltage_{index:02d}": value for index, value in enumerate(cells, 1)})
    names = ("bmsTemperature", "cellTemperature_0104", "cellTemperature_0508",
             "cellTemperature_0912", f"cellTemperature_13{len(cells):02d}")
    for index, value in enumerate(temperatures):
        key = names[index] if index < len(names) else f"cellTemperature_Pos_{index + 1:02d}"
        readings[key] = value
    return readings


def _alarms(data):
    cells = data.vector(1)
    temperatures = data.vector(1)
    codes = {f"almCellVoltage_{index:02d}": value for index, value in enumerate(cells, 1)}
    codes.update({f"almTemperature_{index:02d}": value for index, value in enumerate(temperatures, 1)})
    for key in ("almChargeCurrent", "almModuleVoltage", "almDischargeCurrent"):
        codes[key] = data.integer()
    readings = {key: _ALARMS.get(value, f"unknown (0x{value:02X})") for key, value in codes.items()}
    readings["packAlarmInfo"] = "failure" if any(codes.values()) else "ok"
    return readings


def _charge_limits(data):
    readings = {
        "chargeVoltageLimit": data.integer(2) / 1000,
        "dischargeVoltageLimit": data.integer(2) / 1000,
        "chargeCurrentLimit": data.integer(2) / 10,
        "dischargeCurrentLimit": abs(data.integer(2, signed=True)) / 10,
    }
    flags = data.integer()
    for bit, key in enumerate(("chargeEnable", "dischargeEnable", "chargeImmediatelySOC05",
                               "chargeImmediatelySOC09", "chargeFullRequest")):
        readings[key] = "yes" if flags & (0x80 >> bit) else "no"
    return readings


def _parameters(data):
    readings = {}
    for direction in ("Charge", "Discharge"):
        scope = "Cell" if direction == "Charge" else "Module"
        for limit in ("High", "Low", "Under"):
            readings[f"param{scope}{limit}VoltLimit"] = data.integer(2) / 1000
        for limit in ("High", "Low"):
            readings[f"param{direction}{limit}TempLimit"] = (data.integer(2) - 2731) / 10
        current = data.integer(2)
        readings[f"param{direction}CurrentLimit"] = (
            current if direction == "Charge" else 0xFFFF - current
        ) / 10
    return readings


def _ascii(value):
    return value.decode("ascii", errors="replace").strip("\x00 \xff").replace("-", "")


def parse_readings(command, version, payload):
    """Decode the same eight read commands used by PylonLowVoltage."""
    data = Payload(payload)
    if command == 0x4F:
        return {"protocolVersion": f"V{version >> 4:X}.{version & 15:X}"}
    if command == 0x51:
        model = _ascii(data.take(10))
        data.take(2)
        return {"batteryType": model, "Manufacturer": _ascii(data.take(20))}
    data.take(2 if command in (0x42, 0x44) else 1)
    if command == 0x96:
        vendor = ".".join(str(value) for value in data.take(2))
        mainline = ".".join(str(value) for value in data.take(3))
        return {"moduleSoftwareVersion_manufacture": f"V{vendor}",
                "moduleSoftwareVersion_mainline": f"V{mainline}"}
    if command == 0x93:
        return {"serialNumber": data.take(16).decode("ascii", errors="replace").strip("\x00 ")}
    decoder = {0x42: _analog, 0x44: _alarms, 0x92: _charge_limits, 0x47: _parameters}[command]
    return decoder(data)


def read_command(serial, address, command, *, timeout=None):
    """Write one command and decode its complete carriage-return terminated reply."""
    request = request_frame(address, command)
    serial.reset_read_buffer()
    serial.write(request)
    reply = serial.read_until(b"\r", size=8192, timeout=timeout)
    if reply.endswith(request):
        reply = serial.read_until(b"\r", size=8192, timeout=timeout)
    version, payload = response_payload(reply, address)
    return parse_readings(command, version, payload)


def _probe_module(serial, group, number):
    try:
        read_command(serial, number + 1 + 16 * group, 0x42, timeout=_DISCOVERY_TIMEOUT)
    except _NO_RESPONSE:
        return False
    finally:
        sleep(_COMMAND_DELAY)
    return True


def find_group(serial):
    """Find the first stack whose master replies."""
    return next((group for group in range(8) if _probe_module(serial, group, 1)), None)


def discover_modules(serial):
    """Find the stack and all responding module slots, including gaps."""
    group = find_group(serial)
    if group is None:
        return None
    numbers = [1]
    numbers.extend(number for number in range(2, 17) if _probe_module(serial, group, number))
    return group, numbers


def poll_modules(serial, numbers, group, interval, static_cache, logger):
    """Read numbered modules sequentially and retain successful static reads."""
    modules = {}
    next_request = monotonic()
    for number in numbers:
        started = monotonic()
        address = number + 1 + 16 * group
        readings = {}
        static = static_cache.setdefault(number, {})
        for command in (*_DYNAMIC, *(cmd for cmd in _STATIC if cmd not in static)):
            wait = next_request - monotonic()
            if wait > 0:
                sleep(wait)
            try:
                values = read_command(serial, address, command)
            except _NO_RESPONSE as err:
                logger.debug("Module %d command %02X: %s", number, command, err)
                if command == 0x42:
                    break
                continue
            finally:
                next_request = monotonic() + _COMMAND_DELAY
            if command in _STATIC:
                static[command] = values
            readings.update(values)
        if "packVolt" in readings:
            for values in static.values():
                readings.update(values)
            readings["cmdChainDuration"] = round(monotonic() - started, 3)
            readings["state"] = "connected"
            modules[number] = readings
    next_cycle = datetime.now().astimezone() + interval
    for readings in modules.values():
        readings["nextCycletime"] = next_cycle
    return modules
