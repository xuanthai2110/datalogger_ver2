# drivers/goodwe_gw80kmt.py
#
# GoodWe GW80KMT Modbus RTU Driver
# Tài liệu tham khảo: GoodWe Modbus Protocol of Inverter
#   Grid-tied MTG2/SMT/SDTG2/MS/DNS/XS series (Customer Version)
#
# ┌─────────────────────────────────────────────────────────────────┐
# │  THÔNG SỐ KỸ THUẬT GW80KMT:                                    │
# │    - Công suất định mức AC : 80 kW                              │
# │    - Số MPPT               : 4                                   │
# │    - String / MPPT         : 4                                   │
# │    - Tổng số string        : 16  (addr 859-874)                  │
# │    - 3 pha lưới                                                  │
# │                                                                  │
# │  QUAN TRỌNG - PHÂN VÙNG THANH GHI THEO MODEL:                 │
# │                                                                  │
# │  Dòng 512-566  : Dành cho model NON-MT (DNS/XS/MS...)          │
# │                  *** KHÔNG dùng cho MT/SMT ***                  │
# │                                                                  │
# │  Dòng 768-2003 : Dành cho model MT / SMT (bao gồm GW80KMT)    │
# │    768-800     : Block dữ liệu vận hành MT/SMT                  │
# │    850-896     : Block mở rộng (power, string current, PF, Q)   │
# │    2000-2003   : Control registers                               │
# └─────────────────────────────────────────────────────────────────┘
#
# Thông số truyền thông Modbus RTU:
#   - Baud rate : 9600 bps
#   - Data bits : 8
#   - Parity    : None
#   - Stop bits : 1
#   - Slave ID  : mặc định 247 (có thể thay đổi tại chỗ)
#   - Function  : 03H (Read Holding Registers), 10H (Write Multiple Registers)
#
# Sơ đồ ghép công suất AC 32-bit (MT/SMT):
#   PacH = thanh ghi 850  (high word, unit W)  — dành cho MT/SMT
#   PacL = thanh ghi 781  (low  word, unit W)  — MT/SMT block
#   p_inv_w = (PacH << 16) | PacL
#
#   Lưu ý: Thanh ghi 854 ghi chú "used with register 563" — đó là cặp
#   dành cho NON-MT (563 là PacL non-MT). KHÔNG dùng 854 cho GW80KMT.

from typing import Dict, Any
from backend.drivers.inverters.base import BaseDriver


class Goodwegw80kmt(BaseDriver):

    def __init__(self, transport, slave_id: int = 247):
        self.transport = transport
        self.slave_id = slave_id

    # =========================================================
    # ================= REGISTER MAP ==========================
    # =========================================================

    def register_map(self) -> Dict[str, Any]:
        """
        Bản đồ thanh ghi của GoodWe GW80KMT (dòng MT/SMT).
        Tất cả thanh ghi đọc bằng Function Code 03H (Holding Registers).
        Vùng địa chỉ sử dụng: 512-528 (Device info), 768-800, 850-896
        """
        return {

            # --------------------------------------------------
            # Thông tin thiết bị (chung cho mọi model GoodWe)
            # --------------------------------------------------
            "info": [
                # Serial Number: 8 word = 16 bytes ASCII  (addr 512 = 0x0200)
                {"name": "serial_number", "address": 512, "length": 8, "type": "string",  "scale": None},
                # Device Type: 5 word = 10 bytes ASCII    (addr 528 = 0x0210)
                {"name": "device_type",   "address": 528, "length": 5, "type": "string",  "scale": None},
                # Firmware Version (ARM core)             (addr 852)
                {"name": "fw_version",    "address": 852, "length": 1, "type": "uint16",  "scale": None},
            ],

            # --------------------------------------------------
            # Dữ liệu AC  — vùng MT/SMT block (768-781) + mở rộng
            # --------------------------------------------------
            "ac": [
                # --- Điện áp 3 pha (Unit: 0.1 V) ---
                # Vac1/L1 Phase voltage  addr=772
                {"name": "v_a",     "address": 772, "length": 1, "type": "uint16", "scale": 0.1},
                # Vac2/L2 Phase voltage  addr=773
                {"name": "v_b",     "address": 773, "length": 1, "type": "uint16", "scale": 0.1},
                # Vac3/L3 Phase voltage  addr=774
                {"name": "v_c",     "address": 774, "length": 1, "type": "uint16", "scale": 0.1},

                # --- Dòng điện 3 pha (Unit: 0.1 A) ---
                # Iac1/L1 Phase current  addr=775
                {"name": "i_a",     "address": 775, "length": 1, "type": "uint16", "scale": 0.1},
                # Iac2/L2 Phase current  addr=776
                {"name": "i_b",     "address": 776, "length": 1, "type": "uint16", "scale": 0.1},
                # Iac3/L3 Phase current  addr=777
                {"name": "i_c",     "address": 777, "length": 1, "type": "uint16", "scale": 0.1},

                # --- Tần số lưới 3 pha (Unit: 0.01 Hz) ---
                # Fac1/L1 Phase frequency  addr=778
                {"name": "grid_hz", "address": 778, "length": 1, "type": "uint16", "scale": 0.01},
                # Fac2/L2 Phase frequency  addr=779  (tham khảo, thường = Fac1)
                {"name": "grid_hz_l2", "address": 779, "length": 1, "type": "uint16", "scale": 0.01},
                # Fac3/L3 Phase frequency  addr=780  (tham khảo, thường = Fac1)
                {"name": "grid_hz_l3", "address": 780, "length": 1, "type": "uint16", "scale": 0.01},

                # --- Công suất tác dụng (low word, ghép với PacH=850 trong read_ac) ---
                # PacL: Low word of output power  addr=781  (Unit: 1 W)
                {"name": "p_inv_low",  "address": 781, "length": 1, "type": "uint16", "scale": 1},

                # --- Power Factor  addr=886  (Unit: 0.001) ---
                # Giá trị SF=1000 → scale = 1/1000 = 0.001
                {"name": "pf",         "address": 886, "length": 1, "type": "uint16", "scale": 0.001},

                # --- Công suất phản kháng AC: high byte + low byte (Unit: Var) ---
                # addr 893 = AC reactive power High word  (SF=1000, unit=kVar → 1 unit=1 Var)
                {"name": "q_inv_high", "address": 893, "length": 1, "type": "uint16", "scale": 1},
                # addr 894 = AC reactive power Low  word
                {"name": "q_inv_low",  "address": 894, "length": 1, "type": "uint16", "scale": 1},
            ],

            # --------------------------------------------------
            # Dữ liệu DC — MPPT (MT/SMT block 768-771 + extended 855-858)
            # GW80KMT: 4 MPPT × 2 string = 8 strings tổng
            # --------------------------------------------------
            "dc": [
                # MPPT 1 — Vpv1 (addr 768), Ipv1 (addr 770)  Unit: 0.1 V / 0.1 A
                {"name": "mppt_1_voltage", "address": 768, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_1_current", "address": 770, "length": 1, "type": "uint16", "scale": 0.1},

                # MPPT 2 — Vpv2 (addr 769), Ipv2 (addr 771)
                {"name": "mppt_2_voltage", "address": 769, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_2_current", "address": 771, "length": 1, "type": "uint16", "scale": 0.1},

                # MPPT 3 — Vpv3 (addr 855), Ipv3 (addr 857)  (MT extended block)
                {"name": "mppt_3_voltage", "address": 855, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_3_current", "address": 857, "length": 1, "type": "uint16", "scale": 0.1},

                # MPPT 4 — Vpv4 (addr 856), Ipv4 (addr 858)  (MT extended block)
                {"name": "mppt_4_voltage", "address": 856, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_4_current", "address": 858, "length": 1, "type": "uint16", "scale": 0.1},
            ],

            # --------------------------------------------------
            # Dòng từng string PV — Istr1..Istr16
            # Thanh ghi 859-874  (Unit: 0.1 A, SF=10)
            # GW80KMT: 4 MPPT × 4 string/MPPT = 16 string tổng
            #   MPPT1: String 1-4   (addr 859-862)
            #   MPPT2: String 5-8   (addr 863-866)
            #   MPPT3: String 9-12  (addr 867-870)
            #   MPPT4: String 13-16 (addr 871-874)
            # --------------------------------------------------
            "string": [
                {
                    "name": f"string_{i}_current",
                    "address": 858 + i,   # 859=Istr1 … 874=Istr16
                    "length": 1,
                    "type": "uint16",
                    "scale": 0.1,
                }
                for i in range(1, 17)     # String 1 → 16
            ],

            # --------------------------------------------------
            # Thống kê vận hành — MT/SMT block
            # --------------------------------------------------
            "stat": [
                # Nhiệt độ bên trong inverter  addr=783  (Unit: 0.1 °C, SF=10)
                {"name": "temp_c",        "address": 783, "length": 1, "type": "uint16", "scale": 0.1},

                # Sản lượng ngày hôm nay   addr=800  (Unit: 0.1 kWh, SF=10)
                {"name": "e_daily",       "address": 800, "length": 1, "type": "uint16", "scale": 0.1},

                # Sản lượng tổng High word  addr=786  (Unit: raw, ghép trong read_stat)
                {"name": "e_total_high",  "address": 786, "length": 1, "type": "uint16", "scale": None},
                # Sản lượng tổng Low  word  addr=787
                {"name": "e_total_low",   "address": 787, "length": 1, "type": "uint16", "scale": None},

                # ISO Detection (điện trở cách điện PV)  addr=895  (Unit: kΩ, SF=1)
                {"name": "ir",            "address": 895, "length": 1, "type": "uint16", "scale": 1.0},

                # Warning Code  addr=791  (bit field)
                {"name": "warning_code",  "address": 791, "length": 1, "type": "uint16", "scale": None},
            ],

            # --------------------------------------------------
            # Điều khiển công suất
            # --------------------------------------------------
            "control": [
                # OnGrid Export Power Limit Switch  addr=291  (0=Off, 1=On)
                {"name": "power_limit_switch",  "address": 291, "length": 1, "type": "uint16", "scale": None},
                # Set Export Power Percentage     addr=292  (0-100 %)  — cần bật switch trước
                {"name": "power_limit_percent",  "address": 292, "length": 1, "type": "uint16", "scale": 1.0},
                # Active Power Adjust (direct)    addr=256  (0-100 %) — không cần switch
                {"name": "active_power_adjust",  "address": 256, "length": 1, "type": "uint16", "scale": 1.0},
            ],
        }

    # =========================================================
    # ================= LOW LEVEL READ ========================
    # =========================================================

    def _read_holding(self, start: int, length: int):
        """Đọc holding registers bằng Function Code 03H."""
        response = self.transport.read_holding_registers(
            address=start,
            count=length,
            slave=self.slave_id,
        )
        if response.isError():
            raise Exception(f"Modbus FC03 error tại địa chỉ {start}")
        return response.registers

    def _read_block(self, start: int, length: int):
        """Alias tương thích BaseDriver."""
        return self._read_holding(start, length)

    def _group_contiguous(self, regs: list) -> list:
        """
        Gom nhóm các thanh ghi liên tiếp để giảm số lần giao tiếp Modbus.
        Thanh ghi liên tiếp khi address[i+1] == address[i] + length[i].
        """
        if not regs:
            return []

        ordered = sorted(regs, key=lambda r: r["address"])
        groups = [[ordered[0]]]

        for reg in ordered[1:]:
            prev = groups[-1][-1]
            if reg["address"] == prev["address"] + prev["length"]:
                groups[-1].append(reg)
            else:
                groups.append([reg])

        return groups

    def _read_group(self, regs: list) -> Dict[str, Any]:
        """
        Đọc danh sách thanh ghi, tự động gom nhóm liên tiếp thành
        một lệnh đọc duy nhất để tối ưu băng thông RS-485.
        """
        if not regs:
            return {}

        result = {}
        for group in self._group_contiguous(regs):
            start = group[0]["address"]
            end   = max(r["address"] + r["length"] - 1 for r in group)
            raw   = self._read_holding(start, end - start + 1)

            ordered = []
            for reg in group:
                idx = reg["address"] - start
                ordered.extend(raw[idx: idx + reg["length"]])

            result.update(self.parse(ordered, group))

        return result

    # =========================================================
    # ================= PARSER ================================
    # =========================================================

    def _convert(self, registers, data_type: str):
        """Chuyển đổi raw register(s) → giá trị Python theo kiểu dữ liệu."""
        if not registers:
            return None

        if data_type == "uint16":
            return registers[0] & 0xFFFF

        if data_type == "sint16":
            v = registers[0] & 0xFFFF
            if v & 0x8000:
                v -= 0x10000
            return v

        # GoodWe: thứ tự word → High word trước, Low word sau (big-endian)
        if data_type == "uint32":
            if len(registers) < 2:
                return None
            return ((registers[0] & 0xFFFF) << 16) | (registers[1] & 0xFFFF)

        if data_type == "sint32":
            if len(registers) < 2:
                return None
            v = ((registers[0] & 0xFFFF) << 16) | (registers[1] & 0xFFFF)
            if v & 0x80000000:
                v -= 0x100000000
            return v

        if data_type == "string":
            raw_bytes = bytearray()
            for reg in registers:
                raw_bytes.append((reg >> 8) & 0xFF)
                raw_bytes.append(reg & 0xFF)
            return raw_bytes.decode("ascii", errors="ignore").rstrip("\x00").strip()

        return None

    def parse(self, raw_block, reg_list: list = None) -> Dict[str, Any]:
        """
        Parse raw register block theo danh sách định nghĩa thanh ghi.
        raw_block : list các giá trị word (16-bit) đọc từ Modbus
        reg_list  : danh sách dict thanh ghi từ register_map()
        """
        if reg_list is None:
            return {}

        result = {}
        offset = 0

        for reg in reg_list:
            length = reg["length"]
            raw    = raw_block[offset: offset + length]
            value  = self._convert(raw, reg["type"])

            if value is not None and reg["scale"] is not None:
                value *= reg["scale"]

            result[reg["name"]] = value
            offset += length

        return result

    # =========================================================
    # ================= READ GROUPS ===========================
    # =========================================================

    def read_info(self) -> Dict[str, Any]:
        """
        Đọc thông tin thiết bị.
        Thanh ghi: 512 (Serial), 528 (DeviceType), 852 (FW ARM)
        """
        from datetime import datetime
        try:
            parsed = self._read_group(self.register_map()["info"])
            return {
                "brand":            "GoodWe",
                "model":            "GW80KMT",
                "serial_number":    parsed.get("serial_number", ""),
                "device_type":      parsed.get("device_type", ""),
                "firmware_version": str(parsed.get("fw_version", "1.0")),
                "capacity_kw":      80.0,
                "mppt_count":       4,
                "phase_count":      3,
                "strings_per_mppt": 4,
                "string_count":     16,
                "rate_dc_kwp":      80.0,
                "rate_ac_kw":       80.0,
                "is_active":        True,
                "slave_id":         self.slave_id,
                "usage_start_at":   datetime.now().isoformat(),
                "usage_end_at":     None,
                "replaced_by_id":   None,
            }
        except Exception:
            from datetime import datetime
            return {
                "brand":            "GoodWe",
                "model":            "GW80KMT",
                "serial_number":    "",
                "device_type":      "",
                "firmware_version": "1.0",
                "capacity_kw":      80.0,
                "mppt_count":       4,
                "phase_count":      3,
                "strings_per_mppt": 4,
                "string_count":     16,
                "rate_dc_kwp":      80.0,
                "rate_ac_kw":       80.0,
                "is_active":        False,
                "slave_id":         self.slave_id,
                "usage_start_at":   datetime.now().isoformat(),
                "usage_end_at":     None,
                "replaced_by_id":   None,
            }

    def read_ac(self) -> Dict[str, Any]:
        """
        Đọc dữ liệu AC của inverter GW80KMT (MT series).

        Công suất tác dụng 32-bit (MT/SMT):
          PacH = addr 850  (High word, unit W)  ← dành cho MT
          PacL = addr 781  (Low  word, unit W)  ← MT block
          p_inv_w = (PacH << 16) | PacL

          [Lưu ý] addr 854 "used with register 563" là cặp dành cho
          NON-MT model, KHÔNG áp dụng cho GW80KMT.

        Công suất phản kháng 32-bit (MT):
          q_high = addr 893  (High word, SF=1000 kVar → 1 unit = 1 Var)
          q_low  = addr 894  (Low  word)
          q_inv_var [Var] = (q_high << 16) | q_low  (signed)
        """
        parsed = self._read_group(self.register_map()["ac"])

        # --- PacH: addr 850 (MT/SMT High word of output power) ---
        try:
            pac_h = self._read_holding(850, 1)[0] & 0xFFFF
        except Exception:
            pac_h = 0

        pac_l   = int(parsed.get("p_inv_low", 0) or 0)
        p_inv_w = (pac_h << 16) | pac_l

        # --- Công suất phản kháng 32-bit signed ---
        q_high    = int(parsed.get("q_inv_high", 0) or 0)
        q_low     = int(parsed.get("q_inv_low",  0) or 0)
        q_inv_var = (q_high << 16) | q_low
        if q_inv_var & 0x80000000:
            q_inv_var -= 0x100000000   # chuyển sang signed

        return {
            "v_a":       parsed.get("v_a"),
            "v_b":       parsed.get("v_b"),
            "v_c":       parsed.get("v_c"),
            "i_a":       parsed.get("i_a"),
            "i_b":       parsed.get("i_b"),
            "i_c":       parsed.get("i_c"),
            "grid_hz":   parsed.get("grid_hz"),       # Fac1 L1 (chính)
            "p_inv_w":   p_inv_w,
            "q_inv_var": q_inv_var,
            "pf":        parsed.get("pf"),
        }

    def read_dc(self) -> Dict[str, Any]:
        """
        Đọc dữ liệu DC: điện áp/dòng điện 4 MPPT.
        Tổng công suất DC tính từ P = V×I mỗi MPPT (không có thanh ghi riêng).
        """
        parsed = self._read_group(self.register_map()["dc"])

        p_dc_w = 0.0
        for i in range(1, 5):
            v = parsed.get(f"mppt_{i}_voltage")
            c = parsed.get(f"mppt_{i}_current")
            if v is not None and c is not None:
                p_dc_w += v * c

        parsed["p_dc_w"] = round(p_dc_w)
        return parsed

    def read_string(self) -> Dict[str, Any]:
        """Đọc dòng điện 8 string PV (addr 859-866, unit 0.1A)."""
        return self._read_group(self.register_map()["string"])

    def read_stat(self) -> Dict[str, Any]:
        """
        Đọc thống kê vận hành:
          - temp_c   : Nhiệt độ bên trong (addr 783, 0.1°C)
          - e_daily  : Sản lượng ngày (addr 800, 0.1 kWh)
          - e_total  : Sản lượng tổng ghép 32-bit từ addr 786 (High) + 787 (Low), 0.1 kWh
          - ir       : Điện trở cách điện (addr 895, kΩ)
          - warning_code: Warning code (addr 791)
        """
        regs = self.register_map().get("stat", [])
        if not regs:
            return {}

        parsed = self._read_group(regs)

        # Ghép e_total 32-bit từ High word (786) + Low word (787)
        e_high = parsed.pop("e_total_high", None)
        e_low  = parsed.pop("e_total_low",  None)

        if e_high is not None and e_low is not None:
            e_raw  = ((int(e_high) & 0xFFFF) << 16) | (int(e_low) & 0xFFFF)
            parsed["e_total"] = round(e_raw * 0.1, 1)   # kWh
        else:
            parsed["e_total"] = None

        return parsed

    # =========================================================
    # ================= FAULTS & STATES =======================
    # =========================================================

    def read_states_and_faults(self) -> Dict[str, Any]:
        """
        Đọc trạng thái vận hành và mã lỗi (MT/SMT block):

        WorkMode addr=782:
          0 = cWaitMode   (chờ / self-test)
          1 = cNormalMode (đang phát điện)
          2 = cFaultMode  (lỗi)

        ErrorMessage (32-bit):
          ErrorMessageH addr=784 (High word)
          ErrorMessageL addr=785 (Low  word)
          → fault_code = (H << 16) | L
          Tham khảo bảng Table 8-2 trong tài liệu GoodWe để tra mã lỗi.
        """
        state_id   = 0
        fault_code = 0

        # WorkMode (addr 782)
        try:
            res = self.transport.read_holding_registers(
                address=782, count=1, slave=self.slave_id
            )
            if not res.isError():
                state_id = res.registers[0]
        except Exception:
            pass

        # Error Message H (784) + L (785) → 32-bit fault code
        try:
            res = self.transport.read_holding_registers(
                address=784, count=2, slave=self.slave_id
            )
            if not res.isError() and len(res.registers) >= 2:
                fault_code = ((res.registers[0] & 0xFFFF) << 16) | (res.registers[1] & 0xFFFF)
        except Exception:
            pass

        return {
            "state_id":   state_id,
            "fault_code": fault_code,
        }

    # =========================================================
    # ================= READ POWER ============================
    # =========================================================

    def read_power(self) -> int:
        """
        Đọc công suất AC tức thời (W).
        Ghép từ PacH (addr 850, high word) + PacL (addr 781, low word).
        Lưu ý: addr 854 là cặp non-MT, KHÔNG dùng cho GW80KMT.
        """
        try:
            pac_h = self._read_holding(850, 1)[0] & 0xFFFF
        except Exception:
            pac_h = 0

        try:
            pac_l = self._read_holding(781, 1)[0] & 0xFFFF
        except Exception:
            pac_l = 0

        return int((pac_h << 16) | pac_l)

    # =========================================================
    # ================= READ ALL ==============================
    # =========================================================

    def read_all(self) -> Dict[str, Any]:
        """Đọc tất cả dữ liệu từ inverter GW80KMT và trả về dict tổng hợp."""
        data = {}

        data.update(self.read_info())
        data.update(self.read_ac())

        dc      = self.read_dc()
        strings = self.read_string()
        data.update(dc)
        data.update(strings)

        try:
            data.update(self.read_stat())
        except Exception:
            pass

        try:
            data.update(self.read_states_and_faults())
        except Exception:
            pass

        return data

    # =========================================================
    # ================= CONTROL ===============================
    # =========================================================

    @staticmethod
    def _ensure_write_ok(response, action: str) -> bool:
        if response is None:
            raise Exception(f"{action}: không nhận được phản hồi từ inverter")
        if hasattr(response, "isError") and response.isError():
            raise Exception(f"{action} thất bại: {response}")
        return True

    def enable_power_limit(self, enable: bool) -> bool:
        """
        Bật/tắt chức năng giới hạn công suất xuất lưới.
        Thanh ghi 291 (OnGrid Export Power Limit Switch): 0=Off, 1=On
        """
        response = self.transport.write_register(
            address=291,
            value=1 if enable else 0,
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Enable power limit={enable}")

    def write_power_limit_percent(self, percent: float) -> bool:
        """
        Đặt giới hạn công suất xuất lưới theo % (0-100%).
        Thanh ghi 292 (SetExportPowerPercentage).
        Sẽ tự động bật switch (addr 291) trước khi ghi giá trị.
        """
        self.enable_power_limit(True)
        value = int(max(0, min(100, round(percent))))
        response = self.transport.write_register(
            address=292,
            value=value,
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Write power limit {percent}%")

    def write_power_limit_kw(self, kw: float) -> bool:
        """
        Đặt giới hạn công suất theo kW (quy đổi sang % so với 80 kW định mức).
        """
        percent = (kw / 80.0) * 100.0
        return self.write_power_limit_percent(percent)

    def write_active_power_adjust(self, percent: float) -> bool:
        """
        Điều chỉnh công suất tác dụng trực tiếp qua thanh ghi 256 (0-100%).
        Không cần bật limit switch. Ưu tiên dùng khi cần điều tiết nhanh.
        """
        value = int(max(0, min(100, round(percent))))
        response = self.transport.write_register(
            address=256,
            value=value,
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Write active power adjust {percent}%")

    def read_power_limit(self) -> Dict[str, Any]:
        """Đọc trạng thái và giá trị giới hạn công suất hiện tại."""
        res_sw = self.transport.read_holding_registers(
            address=291, count=1, slave=self.slave_id
        )
        if res_sw.isError():
            raise Exception(f"Đọc power limit switch thất bại: {res_sw}")

        res_val = self.transport.read_holding_registers(
            address=292, count=1, slave=self.slave_id
        )
        if res_val.isError():
            raise Exception(f"Đọc power limit value thất bại: {res_val}")

        mode    = res_sw.registers[0]     # 0=Off, 1=On
        percent = res_val.registers[0]    # 0-100 %

        return {
            "mode":    mode,
            "percent": percent,
            "limit_w": int(percent / 100.0 * 80_000),   # quy đổi sang W
        }

    def read_power_limit_percent(self) -> float:
        try:
            limit = self.read_power_limit()
            if limit.get("mode") == 1:
                return float(limit.get("percent", 100.0))
            return 100.0
        except Exception:
            return 100.0
