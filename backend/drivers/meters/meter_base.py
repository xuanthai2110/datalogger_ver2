"""
backend/drivers/meter_base.py — Base driver cho thiết bị đo lường Meter.

Meter đọc dữ liệu tại điểm đấu nối lưới qua Modbus RTU/TCP.
Các driver cụ thể (Acrel, Eastron, Schneider...) kế thừa class này
và điền register_map theo datasheet của hãng.
"""

import math
import struct
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class MeterDriverBase:
    """
    Base class cho tất cả meter driver.

    Subclass cần override `register_map` với các thanh ghi cụ thể theo hãng.
    Mỗi entry trong register_map:
        "field_name": {
            "address": <int>,       # Địa chỉ thanh ghi bắt đầu
            "count": <int>,         # Số thanh ghi cần đọc (thường 2 cho float)
            "type": "float32" | "uint16" | "int16" | "uint32" | "int32",
            "scale": <float>,       # Hệ số nhân (mặc định 1.0)
            "unit": <str>,          # Đơn vị (kW, kVAr, V, A, Hz...)
        }
    """

    # ===== REGISTER MAP (User sẽ điền cho từng hãng) =====
    register_map: Dict[str, Dict[str, Any]] = {
        # --- Công suất biểu kiến (S) ---
        "s_total":      {"address": 0,  "count": 2, "type": "float32", "scale": 1.0, "unit": "kVA"},
        "s_a":          {"address": 2,  "count": 2, "type": "float32", "scale": 1.0, "unit": "kVA"},
        "s_b":          {"address": 4,  "count": 2, "type": "float32", "scale": 1.0, "unit": "kVA"},
        "s_c":          {"address": 6,  "count": 2, "type": "float32", "scale": 1.0, "unit": "kVA"},
        
        # --- Công suất tác dụng (P) ---
        "p_total":      {"address": 8,  "count": 2, "type": "float32", "scale": 1.0, "unit": "kW"},
        "p_a":          {"address": 10, "count": 2, "type": "float32", "scale": 1.0, "unit": "kW"},
        "p_b":          {"address": 12, "count": 2, "type": "float32", "scale": 1.0, "unit": "kW"},
        "p_c":          {"address": 14, "count": 2, "type": "float32", "scale": 1.0, "unit": "kW"},
        
        # --- Công suất phản kháng (Q) ---
        "q_total":      {"address": 16, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAr"},
        "q_a":          {"address": 18, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAr"},
        "q_b":          {"address": 20, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAr"},
        "q_c":          {"address": 22, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAr"},
        
        # --- Điện áp pha (V_phase) ---
        "v_a":          {"address": 24, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_b":          {"address": 26, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_c":          {"address": 28, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_phase_avg":  {"address": 30, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},

        # --- Điện áp dây (V_line) ---
        "v_ab":         {"address": 32, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_bc":         {"address": 34, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_ca":         {"address": 36, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_line_avg":   {"address": 38, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},

        # --- Dòng điện (I) ---
        "i_a":          {"address": 40, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},
        "i_b":          {"address": 42, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},
        "i_c":          {"address": 44, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},
        "i_avg":        {"address": 46, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},

        # --- Hệ số công suất & Tần số ---
        "pf":           {"address": 48, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "pf_a":         {"address": 50, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "pf_b":         {"address": 52, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "pf_c":         {"address": 54, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "f":            {"address": 56, "count": 2, "type": "float32", "scale": 1.0, "unit": "Hz"},

        # --- Sản lượng TRONG NGÀY (Today) ---
        "exp_st_today": {"address": 58, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAh"},
        "exp_pt_today": {"address": 60, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"},
        "exp_qt_today": {"address": 62, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVArh"},
        "imp_st_today": {"address": 64, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAh"},
        "imp_pt_today": {"address": 66, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"},
        "imp_qt_today": {"address": 68, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVArh"},

        # --- Tổng sản lượng lũy kế (Lifetime) ---
        "e_pt_import":  {"address": 70, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"},
        "e_pt_export":  {"address": 72, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"},
        "e_qt_import":  {"address": 74, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVArh"},
        "e_qt_export":  {"address": 76, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVArh"},
        "e_st_import":  {"address": 78, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAh"},
        "e_st_export":  {"address": 80, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAh"},
    }

    # Đọc input registers (FC04) hay holding registers (FC03)?
    read_function = "input"  # "input" = FC04, "holding" = FC03

    def __init__(self, transport, slave_id: int = 1):
        """
        Args:
            transport: ModbusTCP hoặc ModbusRTU instance.
            slave_id: Địa chỉ slave Modbus của meter.
        """
        self.transport = transport
        self.slave_id = slave_id

    def _read_registers(self, address: int, count: int):
        """Đọc thanh ghi theo read_function (FC03 hoặc FC04)."""
        if self.read_function == "input":
            return self.transport.read_input_registers(address, count, slave=self.slave_id)
        else:
            return self.transport.read_holding_registers(address, count, slave=self.slave_id)

    def _decode_value(self, registers, reg_type: str, scale: float = 1.0) -> Optional[float]:
        """Decode giá trị từ registers theo kiểu dữ liệu."""
        try:
            if reg_type == "float32" and len(registers) >= 2:
                raw = struct.pack(">HH", registers[0], registers[1])
                value = struct.unpack(">f", raw)[0]
                return round(value * scale, 4)
            elif reg_type == "uint16" and len(registers) >= 1:
                return round(registers[0] * scale, 4)
            elif reg_type == "int16" and len(registers) >= 1:
                val = registers[0]
                if val >= 0x8000:
                    val -= 0x10000
                return round(val * scale, 4)
            elif reg_type == "uint32" and len(registers) >= 2:
                val = (registers[0] << 16) | registers[1]
                return round(val * scale, 4)
            elif reg_type == "int32" and len(registers) >= 2:
                val = (registers[0] << 16) | registers[1]
                if val >= 0x80000000:
                    val -= 0x100000000
                return round(val * scale, 4)
        except Exception as e:
            logger.warning(f"[MeterDriver] Decode error: {e}")
        return None

    def read_serial_number(self) -> Optional[str]:
        """
        Đọc Serial Number nếu có thanh ghi tương ứng.
        Nếu không có, trả về None.
        """
        if "serial" in self.register_map:
            reg_info = self.register_map["serial"]
            try:
                response = self._read_registers(reg_info["address"], reg_info["count"])
                if not response.isError():
                    # Decode serial tùy theo type (có thể là float32 chứa số, hoặc string)
                    if reg_info.get("type") == "string":
                        # Giả định string ASCII
                        raw = response.registers
                        chars = []
                        for r in raw:
                            chars.append(chr(r >> 8))
                            chars.append(chr(r & 0xFF))
                        return "".join(chars).strip('\x00').strip()
                    else:
                        val = self._decode_value(response.registers, reg_info.get("type", "float32"))
                        return str(int(val)) if val is not None else None
            except Exception as e:
                logger.warning(f"[MeterDriver] Error reading serial: {e}")
        return None

    def read_all(self) -> Optional[Dict[str, float]]:
        """
        Đọc toàn bộ dữ liệu meter theo register_map.

        Returns:
            dict với các key chuẩn hóa:
                p_total, q_total, s_total,
                v_a, v_b, v_c, v_ab, v_bc, v_ca,
                i_a, i_b, i_c,
                pf, pf_a, pf_b, pf_c, f,
                e_import, e_export
            hoặc None nếu đọc thất bại.
        """
        result = {}
        error_count = 0

        for field_name, reg_info in self.register_map.items():
            try:
                response = self._read_registers(reg_info["address"], reg_info["count"])
                if response.isError():
                    logger.warning(
                        "[MeterDriver] Read error field=%s addr=%s slave=%s: %s",
                        field_name, reg_info["address"], self.slave_id, response,
                    )
                    result[field_name] = 0.0
                    error_count += 1
                    continue

                value = self._decode_value(
                    response.registers,
                    reg_info.get("type", "float32"),
                    reg_info.get("scale", 1.0),
                )
                result[field_name] = value if value is not None else 0.0

            except Exception as e:
                logger.warning("[MeterDriver] Exception reading %s: %s", field_name, e)
                result[field_name] = 0.0
                error_count += 1

        if error_count == len(self.register_map):
            logger.error("[MeterDriver] All reads failed for slave %s", self.slave_id)
            return None

        # 2. Tính toán các trường ảo (Virtual Fields) để bù đắp dữ liệu thiếu
        result = self._compute_virtual_fields(result)
        return result

    def _compute_virtual_fields(self, data: Dict[str, float]) -> Dict[str, float]:
        """Tính toán bù các giá trị thiếu dựa trên các giá trị đã có."""
        
        # --- 1. Tính toán Total nếu có các pha A, B, C ---
        for prefix in ['p', 'q', 's']:
            total_key = f"{prefix}_total"
            if data.get(total_key, 0.0) == 0.0:
                data[total_key] = round(data.get(f"{prefix}_a", 0.0) + 
                                       data.get(f"{prefix}_b", 0.0) + 
                                       data.get(f"{prefix}_c", 0.0), 4)

        # --- 2. Tính toán S nếu có P và Q ---
        for suffix in ['total', 'a', 'b', 'c']:
            s_key = f"s_{suffix}"
            if data.get(s_key, 0.0) == 0.0:
                p = data.get(f"p_{suffix}", 0.0)
                q = data.get(f"q_{suffix}", 0.0)
                if p != 0 or q != 0:
                    data[s_key] = round(math.sqrt(p**2 + q**2), 4)

        # --- 3. Tính toán PF nếu có P và S ---
        for suffix in ['total', 'a', 'b', 'c']:
            pf_key = "pf" if suffix == 'total' else f"pf_{suffix}"
            if data.get(pf_key, 0.0) == 0.0:
                p = abs(data.get(f"p_{suffix}", 0.0))
                s = data.get(f"s_{suffix}", 0.0)
                if s > 0:
                    data[pf_key] = round(p / s, 4)

        # --- 4. Tính toán Averages ---
        if data.get("v_phase_avg", 0.0) == 0.0:
            v_sum = data.get("v_a", 0.0) + data.get("v_b", 0.0) + data.get("v_c", 0.0)
            if v_sum > 0: data["v_phase_avg"] = round(v_sum / 3.0, 2)
            
        if data.get("i_avg", 0.0) == 0.0:
            i_sum = data.get("i_a", 0.0) + data.get("i_b", 0.0) + data.get("i_c", 0.0)
            if i_sum > 0: data["i_avg"] = round(i_sum / 3.0, 4)

        # --- 5. Chuyển đổi V pha sang V dây (ước lượng nếu thiếu hoàn toàn V dây) ---
        if data.get("v_ab", 0.0) == 0.0 and data.get("v_a", 0.0) > 0:
            sqrt3 = math.sqrt(3)
            data["v_ab"] = round(data["v_a"] * sqrt3, 2)
            data["v_bc"] = round(data["v_b"] * sqrt3, 2)
            data["v_ca"] = round(data["v_c"] * sqrt3, 2)
            data["v_line_avg"] = round((data["v_ab"] + data["v_bc"] + data["v_ca"]) / 3.0, 2)

        return data
