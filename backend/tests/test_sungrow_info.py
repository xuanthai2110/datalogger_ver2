import argparse
import json
import os
import sys
from typing import Iterable, List


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.communication.modbus_rtu import ModbusRTU
from backend.core import settings
from backend.drivers.inverters.sungrow_sg110cx import SungrowSG110CX


def _build_transport():
    transport = ModbusRTU(
        port=settings.MODBUS_PORT,
        baudrate=settings.MODBUS_BAUDRATE,
        parity=settings.PARITY,
        stopbits=settings.STOPBITS,
        bytesize=settings.DATABITS,
        timeout=settings.TIMEOUT,
        retries=max(1, settings.RETRIES),
    )

    if not transport.connect():
        raise ConnectionError(
            f"Cannot connect via RTU on {settings.MODBUS_PORT}"
        )

    return transport


def _parse_slave_ids(slave_ids_arg: str | None, slave_start: int, slave_end: int) -> List[int]:
    if slave_ids_arg:
        return [int(item.strip()) for item in slave_ids_arg.split(",") if item.strip()]
    return list(range(slave_start, slave_end + 1))


def _read_one_inverter(transport, slave_id: int, full: bool) -> dict | None:
    driver = SungrowSG110CX(transport, slave_id=slave_id)
    data = driver.read_all() if full else driver.read_info()

    if not data:
        return None

    serial_number = str(data.get("serial_number", "")).strip()
    is_active = bool(data.get("is_active", False))

    if serial_number or is_active:
        data["slave_id"] = slave_id
        return data
    return None


def scan_sungrow_inverters(slave_ids: Iterable[int], full: bool = False) -> List[dict]:
    found = []
    transport = _build_transport()

    try:
        for slave_id in slave_ids:
            try:
                data = _read_one_inverter(transport, slave_id=slave_id, full=full)
                if data:
                    found.append(data)
                    print(
                        f"[FOUND] slave_id={slave_id} "
                        f"serial={data.get('serial_number', '')} "
                        f"model={data.get('model', '')}"
                    )
                else:
                    print(f"[MISS] slave_id={slave_id}")
            except Exception as exc:
                print(f"[ERROR] slave_id={slave_id}: {exc}")
    finally:
        transport.close()

    return found


def main():
    parser = argparse.ArgumentParser(
        description="Doc thong tin tat ca inverter Sungrow SG110CX qua Modbus."
    )
    parser.add_argument("--slave-start", type=int, default=settings.SLAVE_ID_START)
    parser.add_argument("--slave-end", type=int, default=settings.SLAVE_ID_END)
    parser.add_argument(
        "--slave-ids",
        type=str,
        default=None,
        help="Danh sach slave_id cach nhau boi dau phay, vi du: 1,2,5,9",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Doc read_all() thay vi chi read_info()",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ghi ket qua JSON ra file",
    )
    args = parser.parse_args()

    slave_ids = _parse_slave_ids(args.slave_ids, args.slave_start, args.slave_end)

    print("=== SUNGROW INFO SCAN ===")
    print("COMM_TYPE   : RTU")
    print(f"SLAVE_IDS   : {slave_ids}")
    print(f"TARGET      : {settings.MODBUS_PORT}")
    print(f"READ_MODE   : {'read_all' if args.full else 'read_info'}")

    results = scan_sungrow_inverters(slave_ids, full=args.full)

    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nFound {len(results)} inverter(s).")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, ensure_ascii=False)
        print(f"Saved output to {args.output}")


if __name__ == "__main__":
    main()
