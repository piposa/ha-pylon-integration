"""Tests for PylontechParser.parse_pwr."""
import importlib.util
import sys
import types
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "pylontech_serial"


def _load(name):
    pkg = sys.modules.setdefault("pylontech_serial", types.ModuleType("pylontech_serial"))
    pkg.__path__ = [str(PKG)]
    spec = importlib.util.spec_from_file_location(f"pylontech_serial.{name}", PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"pylontech_serial.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_load("structs")
PylontechParser = _load("parser").PylontechParser

OLD = (
    "Power Volt   Curr   Tempr  Tlow   Thigh  Vlow   Vhigh  Base.St  Volt.St  Curr.St  Temp.St  Coulomb  Time                 B.V.St   B.T.St\n"
    "1     50691  3806   17000  13000  14000  3378   3381   Charge   Normal   Normal   Normal   89%      2025-12-21 20:53:06  Normal   Normal\n"
    "2     50673  4087   16000  13000  14000  3377   3380   Charge   Normal   Normal   Normal   87%      2025-12-21 20:53:04  Normal   Normal\n"
    "3     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -\n"
)

# Newer firmware: four extra *.Id columns before Base.St (synthetic, per issue #9)
NEW = (
    "1     50691  3806   17000  13000  14000  3378   3381   1  2  3  4  Charge   Normal   Normal   Normal   89%      2025-12-21 20:53:06  Normal   Normal\n"
    "2     50673  4087   16000  13000  14000  3377   3380   1  2  3  4  Discharge   Normal   Normal   Normal   87%      2025-12-21 20:53:04  Normal   Normal\n"
)


def test_old_layout():
    s = PylontechParser.parse_pwr(OLD)
    assert [(b.sys_id, b.status, b.soc) for b in s.batteries] == [(1, "Charge", 89), (2, "Charge", 87)]


def test_new_layout():
    s = PylontechParser.parse_pwr(NEW)
    assert [(b.sys_id, b.status, b.soc) for b in s.batteries] == [(1, "Charge", 89), (2, "Discharge", 87)]


def test_missing_percent_skipped():
    line = "1     50691  3806   17000  13000  14000  3378   3381   Charge   Normal   Normal   Normal   x  y  z\n"
    assert PylontechParser.parse_pwr(line).batteries == []


rs485 = _load("rs485")


def _response(address, payload):
    encoded = payload.hex().upper()
    length = f"{len(encoded):03X}"
    length_check = -sum(int(digit, 16) for digit in length) & 15
    body = f"20{address:02X}4600{length_check:X}{length}{encoded}".encode()
    return b"~" + body + f"{-sum(body) & 0xFFFF:04X}\r".encode()


def _words(*values):
    return b"".join((value & 0xFFFF).to_bytes(2, "big") for value in values)


def test_rs485_us3000c_analog_readings():
    payload = (
        b"\x00\x02\x0f" + _words(*([3330] * 15))
        + b"\x05" + _words(2931, 2909, 2905, 2907, 2919)
        + _words(-25, 49950, 0) + b"\x04" + _words(0, 347)
        + (58616).to_bytes(3, "big") + (74000).to_bytes(3, "big")
    )
    version, decoded = rs485.response_payload(_response(2, payload), 2)
    readings = rs485.parse_readings(0x42, version, decoded)
    assert [readings[f"cellVoltage_{index:02d}"] for index in range(1, 16)] == [3.33] * 15
    assert readings["bmsTemperature"] == 20
    assert readings["cellTemperature_1315"] == 18.8
    assert readings["numberTempPos"] == 5
    assert readings["packSOC"] == 79.21
    assert readings["packCurrent"] == -2.5
    assert readings["packCycles"] == 347


def test_rs485_six_temperatures_and_small_capacity_format():
    payload = (
        b"\x00\x06\x0f" + _words(*([3300] * 15))
        + b"\x06" + _words(2701, 2731, 2732, 2733, 2734, 2741)
        + _words(0, 49500, 48000) + b"\x02" + _words(50000, 10)
    )
    readings = rs485.parse_readings(0x42, 0x20, payload)
    assert readings["bmsTemperature"] == -3
    assert readings["cellTemperature_Pos_06"] == 1
    assert readings["packSOC"] == 96


def test_rs485_commands_and_frame_validation():
    import pytest

    assert rs485.request_frame(2, 0x42) == b"~20024642E00202FD33\r"
    assert rs485.request_frame(6, 0x4F).startswith(b"~0006464F0000")
    frame = _response(2, b"\x01\x02")
    assert rs485.response_payload(b"\xff\xfd," + frame, 2) == (0x20, b"\x01\x02")
    with pytest.raises(ValueError, match="address"):
        rs485.response_payload(frame, 6)
    with pytest.raises(ValueError, match="checksum"):
        rs485.response_payload(frame[:-5] + b"0000\r", 2)
    with pytest.raises(ValueError, match="Truncated"):
        rs485.parse_readings(0x42, 0x20, b"\x00\x02\x0f")


def test_rs485_alarms_and_charge_management():
    alarms = bytes([0, 2, 2, 0, 0xF0, 1, 2, 0, 0, 0])
    readings = rs485.parse_readings(0x44, 0x20, alarms)
    assert readings["almCellVoltage_02"] == "other error"
    assert readings["almTemperature_01"] == "above higher limit"
    assert readings["packAlarmInfo"] == "failure"
    limits = bytes([2]) + _words(53250, 45000, 370, -370) + bytes([0xC0])
    readings = rs485.parse_readings(0x92, 0x20, limits)
    assert readings["chargeVoltageLimit"] == 53.25
    assert readings["dischargeCurrentLimit"] == 37
    assert readings["chargeEnable"] == "yes"
    assert readings["dischargeEnable"] == "yes"
    assert readings["chargeFullRequest"] == "no"


def test_rs485_static_readings():
    assert rs485.parse_readings(0x4F, 0x20, b"") == {"protocolVersion": "V2.0"}
    assert rs485.parse_readings(0x96, 0x20, bytes([2, 2, 1, 0, 6, 9])) == {
        "moduleSoftwareVersion_manufacture": "V2.1",
        "moduleSoftwareVersion_mainline": "V0.6.9",
    }
    assert rs485.parse_readings(0x51, 0x20, b"US3000C---\x00\x00Pylon---------------") == {
        "batteryType": "US3000C", "Manufacturer": "Pylon",
    }
    parameters = bytes([2]) + _words(3650, 3050, 2800, 3331, 2631, 900,
                                     54000, 46000, 43000, 3331, 2631, 64636)
    readings = rs485.parse_readings(0x47, 0x20, parameters)
    assert readings["paramCellHighVoltLimit"] == 3.65
    assert readings["paramDischargeLowTempLimit"] == -10
    assert readings["paramDischargeCurrentLimit"] == 89.9


def test_rs485_five_modules_and_static_cache(monkeypatch):
    from datetime import timedelta
    import logging

    requests = []

    def read_address(serial, address, command):
        requests.append((address, command))
        if command == 0x42:
            return {"packVolt": 45 + address}
        if command == 0x93:
            return {"serialNumber": f"module-{address}"}
        return {}

    monkeypatch.setattr(rs485, "read_command", read_address)
    monkeypatch.setattr(rs485, "_COMMAND_DELAY", 0)
    cache = {}
    args = (None, range(1, 6), 0, timedelta(seconds=15), cache, logging.getLogger(__name__))
    first = rs485.poll_modules(*args)
    assert list(first) == [1, 2, 3, 4, 5]
    assert first[5]["serialNumber"] == "module-6"
    assert len(requests) == 40
    requests.clear()
    second = rs485.poll_modules(*args)
    assert len(requests) == 15
    assert second[1]["serialNumber"] == "module-2"
    assert second[5]["packVolt"] == 51


def test_rs485_discovery_finds_numbered_modules_after_address_gaps(monkeypatch):
    def read_address(serial, address, command, *, timeout=None):
        assert command == 0x42
        assert timeout is not None
        if address not in (0x22, 0x23, 0x26):
            raise TimeoutError
        return {"packVolt": 49.95}

    monkeypatch.setattr(rs485, "read_command", read_address)
    monkeypatch.setattr(rs485, "_COMMAND_DELAY", 0)
    assert rs485.discover_modules(None) == (2, [1, 2, 5])
