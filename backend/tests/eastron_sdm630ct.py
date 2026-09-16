"""
backend/drivers/eastron_sdm630ct.py — Driver cho Meter Eastron SDM630MCT.
Hỗ trợ đọc dữ liệu tức thời và năng lượng tích lũy qua Modbus RTU/TCP bằng Function Code 04.
"""

import logging
from typing import Dict, Any, Optional
from backend.drivers.meter_base import MeterDriverBase

logger = logging.getLogger(__name__)


class MeterEastronsdm630ct(MeterDriverBase):
    """
    Driver cho Eastron SDM630MCT (3 pha).
    Sử dụng Function Code 04 (Input Registers) cho dữ liệu đo lường.
    Sử dụng Function Code 03 (Holding Registers) cho Serial Number.
    """

    # Eastron SDM630 sử dụng FC04 cho các thanh ghi đo lường
    read_function = "input"

    register_map: Dict[str, Dict[str, Any]] = {
        # --- Điện áp pha (V_phase) ---
        "v_a":          {"address": 0x0000, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_b":          {"address": 0x0002, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_c":          {"address": 0x0004, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_phase_avg":  {"address": 0x002A, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},

        # --- Dòng điện (I) ---
        "i_a":          {"address": 0x0006, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},
        "i_b":          {"address": 0x0008, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},
        "i_c":          {"address": 0x000A, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},
        "i_avg":        {"address": 0x002E, "count": 2, "type": "float32", "scale": 1.0, "unit": "A"},

        # --- Công suất tác dụng (P) ---
        "p_a":          {"address": 0x000C, "count": 2, "type": "float32", "scale": 1.0, "unit": "W"},
        "p_b":          {"address": 0x000E, "count": 2, "type": "float32", "scale": 1.0, "unit": "W"},
        "p_c":          {"address": 0x0010, "count": 2, "type": "float32", "scale": 1.0, "unit": "W"},
        "p_total":      {"address": 0x0034, "count": 2, "type": "float32", "scale": 1.0, "unit": "W"},

        # --- Công suất phản kháng (Q) ---
        "q_a":          {"address": 0x0018, "count": 2, "type": "float32", "scale": 1.0, "unit": "VAr"},
        "q_b":          {"address": 0x001A, "count": 2, "type": "float32", "scale": 1.0, "unit": "VAr"},
        "q_c":          {"address": 0x001C, "count": 2, "type": "float32", "scale": 1.0, "unit": "VAr"},
        "q_total":      {"address": 0x003C, "count": 2, "type": "float32", "scale": 1.0, "unit": "VAr"},

        # --- Công suất biểu kiến (S) ---
        "s_a":          {"address": 0x0012, "count": 2, "type": "float32", "scale": 1.0, "unit": "VA"},
        "s_b":          {"address": 0x0014, "count": 2, "type": "float32", "scale": 1.0, "unit": "VA"},
        "s_c":          {"address": 0x0016, "count": 2, "type": "float32", "scale": 1.0, "unit": "VA"},
        "s_total":      {"address": 0x0038, "count": 2, "type": "float32", "scale": 1.0, "unit": "VA"},

        # --- Hệ số công suất & Tần số ---
        "pf_a":         {"address": 0x001E, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "pf_b":         {"address": 0x0020, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "pf_c":         {"address": 0x0022, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "pf":           {"address": 0x003E, "count": 2, "type": "float32", "scale": 1.0, "unit": ""},
        "f":            {"address": 0x0046, "count": 2, "type": "float32", "scale": 1.0, "unit": "Hz"},

        # --- Điện áp dây (V_line) ---
        "v_ab":         {"address": 0x00C8, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_bc":         {"address": 0x00CA, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_ca":         {"address": 0x00CC, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},
        "v_line_avg":   {"address": 0x00CE, "count": 2, "type": "float32", "scale": 1.0, "unit": "V"},

        # --- Tổng sản lượng lũy kế (Lifetime) ---
        "e_pt_import":  {"address": 0x0048, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"},
        "e_pt_export":  {"address": 0x004A, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"},
        "e_qt_import":  {"address": 0x004C, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVArh"},
        "e_qt_export":  {"address": 0x004E, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVArh"},
        "e_st_import":  {"address": 0x0050, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVAh"},

        # --- Cấu hình Serial (địa chỉ 0xFC00, Holding Register) ---
        "serial":       {"address": 0xFC00, "count": 2, "type": "uint32", "scale": 1.0, "unit": ""},
    }

    def read_serial_number(self) -> Optional[str]:
        """
        Đọc Serial Number từ Holding Register (FC03) tại địa chỉ 0xFC00.
        """
        if "serial" in self.register_map:
            reg_info = self.register_map["serial"]
            try:
                # Đọc bằng holding register (FC03) thay vì read_function là input (FC04)
                response = self.transport.read_holding_registers(
                    reg_info["address"], reg_info["count"], slave=self.slave_id
                )
                if not response.isError():
                    val = self._decode_value(response.registers, reg_info.get("type", "uint32"))
                    return str(int(val)) if val is not None else None
            except Exception as e:
                logger.warning(f"[MeterEastronsdm630ct] Error reading serial: {e}")
        return None
