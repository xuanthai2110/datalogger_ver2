#!/usr/bin/env python3
"""
Test script for reading Solis Hybrid Inverter registers via Modbus TCP.
Compatible with pymodbus 3.6.7+

Registers covered:
  - 43010: Solis Max Charge SOC (%)
  - 43011: Solis Overdischarge SOC (%)
  - 43012: Solis Max Charge Current (A)
  - 43013: Solis Max Discharge Current (A)
  - 43016: Solis Floating Charge Voltage (V)
  - 43017: Solis Equalizing Charge Voltage (V)
  - 43018: Solis Force Charge SOC (%)
  - 43019: Solis Battery Rated Capacity (Ah)
  - 43020: Solis Overdischarge Voltage (V)
  - 43021: Solis Forcecharge Voltage (V)
  - 43024: Solis Backup SOC (%)
  - 43027: Solis Force-charge Power Limitation (W)
  - 43074: Solis Backflow Power (W)
  - 43081: Solis Output Power Clamp (W)
  - 43117: Solis Battery Max Charge Current (A)
  - 43118: Solis Battery Max Discharge Current (A)
  - 43128: Solis RC Inverter AC Grid Active Power (W)
  - 43129: Solis RC Force Battery Discharge Power (W)
  - 43130: Solis Battery Charge Limit Power (W)
  - 43131: Solis Battery Discharge Limit Power (W)
  - 43133: Solis RC Grid Active Power (W)
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# List of 21 registers specified in the configuration table
REGISTER_TABLE = [
    {"reg": 43010, "name": "Solis Max Charge SOC", "unit": "%", "scale": 1.0, "type": "uint16"},
    {"reg": 43011, "name": "Solis Overdischarge SOC", "unit": "%", "scale": 1.0, "type": "uint16"},
    {"reg": 43012, "name": "Solis Max Charge Current", "unit": "A", "scale": 0.1, "type": "uint16"},
    {"reg": 43013, "name": "Solis Max Discharge Current", "unit": "A", "scale": 0.1, "type": "uint16"},
    {"reg": 43016, "name": "Solis Floating Charge Voltage", "unit": "V", "scale": 0.1, "type": "uint16"},
    {"reg": 43017, "name": "Solis Equalizing Charge Voltage", "unit": "V", "scale": 0.1, "type": "uint16"},
    {"reg": 43018, "name": "Solis Force Charge SOC", "unit": "%", "scale": 1.0, "type": "uint16"},
    {"reg": 43019, "name": "Solis Battery Rated Capacity", "unit": "Ah", "scale": 1.0, "type": "uint16"},
    {"reg": 43020, "name": "Solis Overdischarge Voltage", "unit": "V", "scale": 0.1, "type": "uint16"},
    {"reg": 43021, "name": "Solis Forcecharge Voltage", "unit": "V", "scale": 0.1, "type": "uint16"},
    {"reg": 43024, "name": "Solis Backup SOC", "unit": "%", "scale": 1.0, "type": "uint16"},
    {"reg": 43027, "name": "Solis Force-charge Power Limitation", "unit": "W", "scale": 1.0, "type": "uint16"},
    {"reg": 43074, "name": "Solis Backflow Power", "unit": "W", "scale": 1.0, "type": "int16"},
    {"reg": 43081, "name": "Solis Output Power Clamp", "unit": "W", "scale": 1.0, "type": "uint16"},
    {"reg": 43117, "name": "Solis Battery Max Charge Current", "unit": "A", "scale": 0.1, "type": "uint16"},
    {"reg": 43118, "name": "Solis Battery Max Discharge Current", "unit": "A", "scale": 0.1, "type": "uint16"},
    {"reg": 43128, "name": "Solis RC Inverter AC Grid Active Power", "unit": "W", "scale": 1.0, "type": "int16"},
    {"reg": 43129, "name": "Solis RC Force Battery Discharge Power", "unit": "W", "scale": 1.0, "type": "uint16"},
    {"reg": 43130, "name": "Solis Battery Charge Limit Power", "unit": "W", "scale": 1.0, "type": "uint16"},
    {"reg": 43131, "name": "Solis Battery Discharge Limit Power", "unit": "W", "scale": 1.0, "type": "uint16"},
    {"reg": 43133, "name": "Solis RC Grid Active Power", "unit": "W", "scale": 1.0, "type": "int16"},
]


def calculate_modbus_address(reg_num: int, offset_mode: str) -> int:
    """Calculate Modbus register address based on offset mode."""
    if offset_mode == "40001":
        return reg_num - 40001
    elif offset_mode == "40000":
        return reg_num - 40000
    elif offset_mode == "raw":
        return reg_num
    else:
        # Default: 40001 offset
        return reg_num - 40001


def parse_register_value(raw_val: int, data_type: str, scale: float) -> tuple[float, str]:
    """Convert raw uint16 register to signed/unsigned value and scaled value."""
    if data_type == "int16":
        # Convert unsigned uint16 to signed 16-bit int
        val = raw_val if raw_val < 0x8000 else raw_val - 0x10000
    else:
        val = raw_val

    scaled_val = val * scale
    return scaled_val, f"0x{raw_val:04X} ({raw_val})"


def read_registers_single(client: ModbusTcpClient, slave_id: int, offset_mode: str):
    """Read each register individually (safest for non-contiguous registers)."""
    results = []
    success_count = 0

    for item in REGISTER_TABLE:
        reg_num = item["reg"]
        modbus_addr = calculate_modbus_address(reg_num, offset_mode)

        try:
            try:
                res = client.read_holding_registers(address=modbus_addr, count=1, slave=slave_id)
            except TypeError:
                res = client.read_holding_registers(address=modbus_addr, count=1, unit=slave_id)

            if res is None or res.isError():
                results.append((item, None, f"ERROR: {res}"))
            else:
                raw_val = res.registers[0]
                scaled_val, hex_str = parse_register_value(raw_val, item["type"], item["scale"])
                results.append((item, scaled_val, hex_str))
                success_count += 1
        except Exception as e:
            results.append((item, None, f"EXCEPT: {e}"))

    return results, success_count


def display_results(results, success_count: int, total_count: int, host: str, slave_id: int, offset_mode: str):
    """Print results in a clean formatted table."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 90, flush=True)
    print(f" SOLIS MODBUS TCP READ RESULT | Time: {now_str}", flush=True)
    print(f" Host: {host} | Slave ID: {slave_id} | Offset Mode: {offset_mode} | Success: {success_count}/{total_count}", flush=True)
    print("=" * 90, flush=True)
    print(f"{'Reg 4xxxx':<10} | {'Addr':<6} | {'Thanh ghi / Name':<38} | {'Raw (Hex)':<12} | {'Gia tri (Value)':<12} | {'Don vi'}", flush=True)
    print("-" * 90, flush=True)

    for item, val, raw_info in results:
        reg_num = item["reg"]
        modbus_addr = calculate_modbus_address(reg_num, offset_mode)
        name = item["name"]
        unit = item["unit"]

        if val is not None:
            val_str = f"{val:.1f}" if isinstance(val, float) and not val.is_integer() else f"{int(val)}"
            print(f"{reg_num:<10} | {modbus_addr:<6} | {name:<38} | {raw_info:<12} | {val_str:<12} | {unit}", flush=True)
        else:
            print(f"{reg_num:<10} | {modbus_addr:<6} | {name:<38} | {raw_info:<12} | {'N/A':<12} | {unit}", flush=True)

    print("=" * 90 + "\n", flush=True)


def safe_int_env(env_name: str, default_val: int) -> int:
    """Safely parse integer environment variable, falling back to default if invalid."""
    val = os.environ.get(env_name)
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return default_val


def safe_float_env(env_name: str, default_val: float) -> float:
    """Safely parse float environment variable, falling back to default if invalid."""
    val = os.environ.get(env_name)
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return default_val


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test Modbus TCP reader for Solis Hybrid Inverter registers."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MODBUS_HOST", "192.168.1.100"),
        help="IP address of Modbus TCP inverter / gateway (default: 192.168.1.100)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=safe_int_env("MODBUS_PORT", 502),
        help="Modbus TCP port (default: 502)",
    )
    parser.add_argument(
        "--slave",
        type=int,
        default=safe_int_env("MODBUS_SLAVE", 1),
        help="Modbus Slave Unit ID (default: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=safe_float_env("MODBUS_TIMEOUT", 3.0),
        help="Socket timeout in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--offset-mode",
        choices=["40001", "40000", "raw"],
        default=os.environ.get("OFFSET_MODE", "40001"),
        help="Address offset calculation mode: 40001 (reg - 40001 = addr 3009), 40000 (reg - 40000 = addr 3010), raw (reg directly). Default: 40001",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=safe_int_env("READ_INTERVAL", 0),
        help="Repeat reading interval in seconds (default: 0 = read once and exit)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"[@] Connecting to Modbus TCP -> {args.host}:{args.port} (Slave ID: {args.slave}, Timeout: {args.timeout}s)...", flush=True)
    try:
        client = ModbusTcpClient(host=args.host, port=args.port, timeout=args.timeout)
    except Exception as e:
        print(f"[!] ERROR initializing ModbusTcpClient: {e}", flush=True)
        sys.exit(1)

    if not client.connect():
        print(f"[!] ERROR: Failed to connect to Modbus TCP server at {args.host}:{args.port}", flush=True)
        sys.exit(1)

    print(f"[+] Connected to {args.host}:{args.port} successfully.", flush=True)

    try:
        while True:
            results, success_count = read_registers_single(client, args.slave, args.offset_mode)
            display_results(results, success_count, len(REGISTER_TABLE), args.host, args.slave, args.offset_mode)

            if args.interval <= 0:
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[*] Stopped by user.", flush=True)
    finally:
        client.close()
        print("[+] Connection closed.", flush=True)


if __name__ == "__main__":
    main()

