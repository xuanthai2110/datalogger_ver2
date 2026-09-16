"""
test_goodwe_gw80kmt.py
======================
Script test đọc toàn bộ dữ liệu inverter GoodWe GW80KMT qua Modbus RTU
và build telemetry payload giống như hệ thống gửi lên server.

Cách dùng:
    python test_goodwe_gw80kmt.py [--port PORT] [--slave SLAVE_ID] [--baud BAUD]

Ví dụ:
    python test_goodwe_gw80kmt.py --port COM3 --slave 247 --baud 9600
    python test_goodwe_gw80kmt.py --port /dev/ttyUSB0 --slave 247

Kết quả:
    - In ra console toàn bộ dữ liệu đọc được từng nhóm (raw)
    - In ra payload JSON giống format gửi server
    - Lưu payload vào file goodwe_test_result.json
"""

import sys
import json
import logging
import argparse
from datetime import datetime

# Thêm đường dẫn project vào sys.path
sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("TestGoodWeGW80KMT")

# ─────────────────────────────────────────────
# Import các module của project
# ─────────────────────────────────────────────
from backend.communication.modbus_rtu import ModbusRTU
from backend.drivers.inverters.goodwe_gw80kmt import Goodwegw80kmt
from backend.services.normalization_service import NormalizationService


# ─────────────────────────────────────────────
# Hằng số thông số kỹ thuật GW80KMT
# ─────────────────────────────────────────────
MPPT_COUNT       = 4
STRINGS_PER_MPPT = 4
STRING_COUNT     = 16
CAPACITY_KW      = 80.0


# =========================================================
# BUILD TELEMETRY PAYLOAD (giống TelemetryService)
# =========================================================

def _num(value, default=0.0):
    """Chuyển về float, trả về default nếu None hoặc không hợp lệ."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_ts(ts=None):
    """Format timestamp theo chuẩn ISO8601 +07:00."""
    if ts is None:
        ts = datetime.now().isoformat()
    if "T" not in ts:
        ts = ts.replace(" ", "T")
    if "+" not in ts and not ts.endswith("Z"):
        ts += "+07:00"
    return ts


def build_telemetry_payload(clean: dict, raw: dict, timestamp: str) -> dict:
    """
    Xây dựng telemetry payload từ dữ liệu đã chuẩn hoá của inverter GW80KMT.
    Format giống hệ thống gửi server (TelemetryService.build_payload_from_cache).

    Cấu trúc payload:
    {
        "project": { P_ac, P_dc, E_daily, E_total, Temp_C, severity, created_at },
        "inverters": [
            {
                "serial_number": ...,
                "ac": { V_a, V_b, V_c, I_a, I_b, I_c, P_ac, Q_ac, PF, H,
                        Temp_C, IR, E_daily, E_total, E_monthly, created_at },
                "mppts": [
                    {
                        "mppt_index": 1..4,
                        "string_on_mppt": 4,
                        "V_mppt": ..., "I_mppt": ..., "P_mppt": ...,
                        "created_at": ...,
                        "strings": [
                            { "string_index": 1..16, "I_mppt": ..., "created_at": ... }
                        ]
                    }
                ],
                "errors": [
                    { "fault_code", "fault_description", "severity", "created_at" }
                ]
            }
        ]
    }
    """
    ts = _fmt_ts(timestamp)

    # ── 1. Dữ liệu AC (W → kW, var → kvar) ──────────────────────────────────
    p_ac_w   = _num(clean.get("p_inv_w"))
    q_ac_var = _num(clean.get("q_inv_var"))
    p_dc_w   = _num(clean.get("p_dc_w"))
    e_daily  = _num(clean.get("e_daily"))
    e_total  = _num(clean.get("e_total"))
    temp_c   = _num(clean.get("temp_c"))
    ir       = _num(clean.get("ir"))

    ac_section = {
        "IR":       round(ir, 2),
        "Temp_C":   round(temp_c, 2),
        "P_ac":     round(p_ac_w, 2),          # W (giữ nguyên đơn vị W như server)
        "Q_ac":     round(q_ac_var, 2),         # var
        "V_a":      round(_num(clean.get("v_a")), 2),
        "V_b":      round(_num(clean.get("v_b")), 2),
        "V_c":      round(_num(clean.get("v_c")), 2),
        "I_a":      round(_num(clean.get("i_a")), 2),
        "I_b":      round(_num(clean.get("i_b")), 2),
        "I_c":      round(_num(clean.get("i_c")), 2),
        "PF":       round(_num(clean.get("pf")), 4),
        "H":        round(_num(clean.get("grid_hz")), 2),
        "E_daily":  round(e_daily, 2),
        "E_monthly": 0.0,                       # tính ở server
        "E_total":  round(e_total, 2),
        "created_at": ts,
    }

    # ── 2. MPPT + String ─────────────────────────────────────────────────────
    mppt_list = []
    for mppt_idx in range(1, MPPT_COUNT + 1):
        v_mppt = _num(clean.get(f"mppt_{mppt_idx}_voltage"))
        i_mppt = _num(clean.get(f"mppt_{mppt_idx}_current"))
        p_mppt = round(v_mppt * i_mppt, 2)

        # String index cho MPPT này: 4 string liên tiếp
        str_start = (mppt_idx - 1) * STRINGS_PER_MPPT + 1   # 1,5,9,13
        str_end   = str_start + STRINGS_PER_MPPT             # 5,9,13,17 (exclusive)

        strings_section = []
        for str_idx in range(str_start, str_end):
            i_str = _num(clean.get(f"string_{str_idx}_current"))
            strings_section.append({
                "string_index": str_idx,
                "I_mppt":       round(i_str, 2),
                "Max_I":        0.0,            # tracking service tính
                "created_at":   ts,
            })

        mppt_list.append({
            "mppt_index":    mppt_idx,
            "string_on_mppt": STRINGS_PER_MPPT,
            "V_mppt":        round(v_mppt, 2),
            "I_mppt":        round(i_mppt, 2),
            "P_mppt":        p_mppt,
            "Max_I":         0.0,
            "Max_V":         0.0,
            "Max_P":         0.0,
            "created_at":    ts,
            "strings":       strings_section,
        })

    # ── 3. Error / Status ─────────────────────────────────────────────────────
    state_id   = raw.get("state_id", 0)
    fault_code = raw.get("fault_code", 0)

    # GoodWe WorkMode: 0=Wait, 1=Normal, 2=Fault
    state_map = {
        0: ("SLEEPING",  "STABLE"),
        1: ("RUNNING",   "STABLE"),
        2: ("FAULT",     "ERROR"),
    }
    state_text, severity = state_map.get(state_id, ("UNKNOWN", "STABLE"))

    if fault_code != 0:
        severity = "ERROR"

    errors_section = [{
        "fault_code":        fault_code,
        "fault_description": state_text,
        "repair_instruction": (
            "Kiểm tra bảng Table 8-2 trong tài liệu GoodWe Modbus Protocol"
            if fault_code != 0 else ""
        ),
        "severity":  severity,
        "created_at": ts,
    }]

    # ── 4. Inverter section ───────────────────────────────────────────────────
    serial_number = raw.get("serial_number", "")
    inv_section = {
        "serial_number": serial_number,
        "ac":     ac_section,
        "mppts":  mppt_list,
        "errors": errors_section,
    }

    # ── 5. Project summary ────────────────────────────────────────────────────
    project_section = {
        "Temp_C":    round(temp_c, 2),
        "P_ac":      round(p_ac_w, 2),
        "P_dc":      round(p_dc_w, 2),
        "E_daily":   round(e_daily, 2),
        "E_monthly": 0.0,
        "E_total":   round(e_total, 2),
        "severity":  severity,
        "created_at": ts,
    }

    return {
        "project":   project_section,
        "inverters": [inv_section],
    }


# =========================================================
# PRINT HELPER
# =========================================================

SEP = "─" * 70

def print_section(title: str, data: dict):
    print(f"\n{'═'*70}")
    print(f"  {title}")
    print(f"{'═'*70}")
    for k, v in data.items():
        if v is None:
            print(f"  {k:<30s} = None")
        elif isinstance(v, float):
            print(f"  {k:<30s} = {v:.4f}")
        else:
            print(f"  {k:<30s} = {v}")


# =========================================================
# MAIN
# =========================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Test đọc dữ liệu GoodWe GW80KMT qua Modbus RTU"
    )
    parser.add_argument("--port",  default="COM3",        help="Cổng COM/USB (mặc định: COM3)")
    parser.add_argument("--slave", type=int, default=247, help="Slave ID (mặc định: 247)")
    parser.add_argument("--baud",  type=int, default=9600,help="Baud rate (mặc định: 9600)")
    parser.add_argument("--timeout", type=float, default=3.0, help="Timeout giây (mặc định: 3.0)")
    parser.add_argument("--retries", type=int, default=3, help="Số lần thử lại (mặc định: 3)")
    return parser.parse_args()


def main():
    args = parse_args()

    logger.info("=" * 70)
    logger.info("  TEST GoodWe GW80KMT — Modbus RTU")
    logger.info("=" * 70)
    logger.info(f"  Cổng    : {args.port}")
    logger.info(f"  Slave ID: {args.slave}")
    logger.info(f"  Baud    : {args.baud} bps  |  8N1")
    logger.info(f"  Timeout : {args.timeout}s   |  Retries: {args.retries}")
    logger.info("=" * 70)

    # ── Kết nối Modbus RTU ────────────────────────────────────────────────────
    transport = ModbusRTU(
        port=args.port,
        baudrate=args.baud,
        parity="N",
        stopbits=1,
        bytesize=8,
        timeout=args.timeout,
        retries=args.retries,
    )

    if not transport.connect():
        logger.error(f"❌ Không thể mở cổng {args.port}. Kiểm tra lại kết nối RS485.")
        sys.exit(1)

    logger.info(f"✅ Kết nối thành công tới {args.port}")

    try:
        driver = Goodwegw80kmt(transport, slave_id=args.slave)
        normalization = NormalizationService()
        timestamp = datetime.now().isoformat()

        # ── 1. Đọc thông tin thiết bị ─────────────────────────────────────────
        print(f"\n{SEP}")
        print("  [1/6] Đọc thông tin thiết bị (Device Info)")
        print(SEP)
        try:
            info = driver.read_info()
            for k, v in info.items():
                print(f"  {k:<25s} = {v}")
        except Exception as e:
            logger.error(f"Lỗi đọc Info: {e}")
            info = {}

        # ── 2. Đọc dữ liệu AC ────────────────────────────────────────────────
        print(f"\n{SEP}")
        print("  [2/6] Đọc dữ liệu AC (Điện áp / Dòng điện / Công suất)")
        print(SEP)
        try:
            ac_raw = driver.read_ac()
            for k, v in ac_raw.items():
                unit = {
                    "v_a": "V", "v_b": "V", "v_c": "V",
                    "i_a": "A", "i_b": "A", "i_c": "A",
                    "grid_hz": "Hz", "p_inv_w": "W", "q_inv_var": "var", "pf": "",
                }.get(k, "")
                vstr = f"{v:.3f}" if isinstance(v, float) else str(v)
                print(f"  {k:<20s} = {vstr:>12s}  {unit}")
        except Exception as e:
            logger.error(f"Lỗi đọc AC: {e}")
            ac_raw = {}

        # ── 3. Đọc dữ liệu DC (MPPT) ─────────────────────────────────────────
        print(f"\n{SEP}")
        print("  [3/6] Đọc dữ liệu DC (4 MPPT)")
        print(SEP)
        try:
            dc_raw = driver.read_dc()
            print(f"  {'Tên':<25s}  {'Giá trị':>10s}  Đơn vị")
            print(f"  {'-'*50}")
            for k, v in dc_raw.items():
                if k == "p_dc_w":
                    print(f"  {k:<25s}  {v:>10.1f}  W (tính toán)")
                elif "voltage" in k:
                    vstr = f"{v:.1f}" if isinstance(v, float) else str(v)
                    print(f"  {k:<25s}  {vstr:>10s}  V")
                elif "current" in k:
                    vstr = f"{v:.2f}" if isinstance(v, float) else str(v)
                    print(f"  {k:<25s}  {vstr:>10s}  A")
                else:
                    print(f"  {k:<25s}  {v}")
        except Exception as e:
            logger.error(f"Lỗi đọc DC: {e}")
            dc_raw = {}

        # ── 4. Đọc dòng từng string ───────────────────────────────────────────
        print(f"\n{SEP}")
        print("  [4/6] Đọc dòng string PV (16 string, addr 859-874)")
        print(SEP)
        try:
            string_raw = driver.read_string()
            print(f"  {'String':<15s}  {'Addr':>6s}  {'Dòng (A)':>10s}")
            print(f"  {'-'*35}")
            for mppt_idx in range(1, MPPT_COUNT + 1):
                str_start = (mppt_idx - 1) * STRINGS_PER_MPPT + 1
                for s in range(str_start, str_start + STRINGS_PER_MPPT):
                    key  = f"string_{s}_current"
                    addr = 858 + s
                    val  = string_raw.get(key)
                    vstr = f"{val:.2f}" if isinstance(val, float) else "None"
                    flag = "  ← MPPT" + str(mppt_idx) + " bắt đầu" if s == str_start else ""
                    print(f"  {key:<22s}  [{addr}]  {vstr:>8s} A{flag}")
        except Exception as e:
            logger.error(f"Lỗi đọc String: {e}")
            string_raw = {}

        # ── 5. Đọc thống kê (Stat) ────────────────────────────────────────────
        print(f"\n{SEP}")
        print("  [5/6] Đọc thống kê vận hành (Temp / Energy / ISO)")
        print(SEP)
        try:
            stat_raw = driver.read_stat()
            stat_units = {
                "temp_c": "°C", "e_daily": "kWh", "e_total": "kWh",
                "ir": "kΩ", "warning_code": "(bit field)"
            }
            for k, v in stat_raw.items():
                unit = stat_units.get(k, "")
                vstr = f"{v:.2f}" if isinstance(v, float) else str(v)
                print(f"  {k:<20s} = {vstr:>12s}  {unit}")
        except Exception as e:
            logger.error(f"Lỗi đọc Stat: {e}")
            stat_raw = {}

        # ── 6. Đọc trạng thái & lỗi ──────────────────────────────────────────
        print(f"\n{SEP}")
        print("  [6/6] Đọc trạng thái & mã lỗi (WorkMode / ErrorMessage)")
        print(SEP)
        try:
            state_raw = driver.read_states_and_faults()
            state_id   = state_raw.get("state_id", 0)
            fault_code = state_raw.get("fault_code", 0)
            state_names = {0: "cWaitMode (chờ/self-test)", 1: "cNormalMode (phát điện)", 2: "cFaultMode (lỗi)"}
            print(f"  state_id   (addr 782) = {state_id}  → {state_names.get(state_id, 'Unknown')}")
            print(f"  fault_code (addr 784-785) = 0x{fault_code:08X}  ({fault_code})")
            if fault_code != 0:
                print(f"  ⚠️  Có lỗi! Tra bảng Table 8-2 trong tài liệu GoodWe để xác định nguyên nhân.")
                for bit in range(32):
                    if fault_code & (1 << bit):
                        print(f"       Bit {bit:2d} (0x{(1<<bit):08X}) bị set")
        except Exception as e:
            logger.error(f"Lỗi đọc States: {e}")
            state_raw = {}

        # ── Gộp toàn bộ raw data ──────────────────────────────────────────────
        raw_all = {}
        raw_all.update(info)
        raw_all.update(ac_raw)
        raw_all.update(dc_raw)
        raw_all.update(string_raw)
        raw_all.update(stat_raw)
        raw_all.update(state_raw)

        # ── Chuẩn hoá ─────────────────────────────────────────────────────────
        print(f"\n{SEP}")
        print("  [NORMALIZE] Chuẩn hoá dữ liệu (NormalizationService)")
        print(SEP)
        clean = normalization.normalize(raw_all)

        # Kiểm tra cảnh báo
        warnings = normalization.validate_snapshot(raw_all)
        if warnings:
            print(f"  ⚠️  Cảnh báo validation ({len(warnings)} field):")
            for wk, wmsg in warnings.items():
                print(f"     {wk}: {wmsg}")
        else:
            print("  ✅ Tất cả giá trị trong khoảng hợp lệ.")

        # ── Build telemetry payload ───────────────────────────────────────────
        print(f"\n{'═'*70}")
        print("  BUILD TELEMETRY PAYLOAD (giống format gửi server)")
        print(f"{'═'*70}")
        payload = build_telemetry_payload(clean, raw_all, timestamp)

        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        print(payload_json)

        # ── Lưu vào file ──────────────────────────────────────────────────────
        out_file = "goodwe_test_result.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp":      timestamp,
                "port":           args.port,
                "slave_id":       args.slave,
                "raw_data":       {
                    k: (v if not isinstance(v, float) else round(v, 4))
                    for k, v in raw_all.items()
                },
                "clean_data":     {
                    k: (v if not isinstance(v, float) else round(v, 4))
                    for k, v in clean.items()
                },
                "telemetry_payload": payload,
            }, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Đã lưu kết quả vào file: {out_file}")

        # ── Tóm tắt nhanh ─────────────────────────────────────────────────────
        print(f"\n{'═'*70}")
        print("  TÓM TẮT")
        print(f"{'═'*70}")
        print(f"  Serial Number   : {raw_all.get('serial_number', 'N/A')}")
        print(f"  Device Type     : {raw_all.get('device_type',   'N/A')}")
        print(f"  Firmware (ARM)  : {raw_all.get('fw_version',    'N/A')}")
        print(f"  Công suất AC    : {_num(clean.get('p_inv_w')):>12.1f}  W")
        print(f"  Công suất DC    : {_num(clean.get('p_dc_w')):>12.1f}  W")
        print(f"  Sản lượng ngày  : {_num(clean.get('e_daily')):>12.2f}  kWh")
        print(f"  Sản lượng tổng  : {_num(clean.get('e_total')):>12.2f}  kWh")
        print(f"  Nhiệt độ        : {_num(clean.get('temp_c')):>12.1f}  °C")
        print(f"  Điện trở cách điện : {_num(clean.get('ir')):>8.1f}  kΩ")
        print(f"  WorkMode        : {raw_all.get('state_id', 'N/A')}")
        print(f"  Fault Code      : 0x{int(raw_all.get('fault_code', 0)):08X}")
        print(f"{'═'*70}\n")

    except KeyboardInterrupt:
        logger.info("Ngừng test theo yêu cầu người dùng.")
    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng: {e}", exc_info=True)
    finally:
        transport.close()
        logger.info("Đã đóng cổng Modbus RTU.")


if __name__ == "__main__":
    main()
