"""
backend/drivers/acrel_dtsd1352.py — Driver cho Meter Acrel DTSD1352.
Hỗ trợ đọc dữ liệu tức thời và năng lượng tích lũy qua Modbus RTU/TCP bằng Function Code 03.
"""

import logging
from typing import Dict, Any, Optional
from backend.drivers.meters.meter_base import MeterDriverBase

logger = logging.getLogger(__name__)


class MeterAcreldtsd1352(MeterDriverBase):
    """
    Driver cho Acrel DTSD1352 (3 pha).
    Sử dụng Function Code 03 (Holding Registers).
    """

    # Acrel DTSD1352 sử dụng FC03 cho tất cả các vùng địa chỉ này
    read_function = "holding"

    register_map: Dict[str, Dict[str, Any]] = {
        # === NHÓM 1: DỮ LIỆU ĐIỆN ÁP PHA (0.1 V) ===
        "v_a":          {"address": 0x0061, "count": 1, "type": "uint16", "scale": 0.1, "unit": "V"},
        "v_b":          {"address": 0x0062, "count": 1, "type": "uint16", "scale": 0.1, "unit": "V"},
        "v_c":          {"address": 0x0063, "count": 1, "type": "uint16", "scale": 0.1, "unit": "V"},

        # === NHÓM 2: DỮ LIỆU DÒNG ĐIỆN (0.01 A) ===
        "i_a":          {"address": 0x0064, "count": 1, "type": "uint16", "scale": 0.01, "unit": "A"},
        "i_b":          {"address": 0x0065, "count": 1, "type": "uint16", "scale": 0.01, "unit": "A"},
        "i_c":          {"address": 0x0066, "count": 1, "type": "uint16", "scale": 0.01, "unit": "A"},

        # === NHÓM 3: TẦN SỐ (0.01 Hz) ===
        "f":            {"address": 0x0077, "count": 1, "type": "uint16", "scale": 0.01, "unit": "Hz"},

        # === NHÓM 4: ĐIỆN ÁP DÂY (0.1 V) ===
        "v_ab":         {"address": 0x0078, "count": 1, "type": "uint16", "scale": 0.1, "unit": "V"},
        "v_bc":         {"address": 0x0079, "count": 1, "type": "uint16", "scale": 0.1, "unit": "V"},
        "v_ca":         {"address": 0x007A, "count": 1, "type": "uint16", "scale": 0.1, "unit": "V"},

        # === NHÓM 5: CÔNG SUẤT TÁC DỤNG (int32 có dấu, scale 0.001 kW = 1W) ===
        # P_total = data * PT * CT * 0.001 kW. Do scale của driver quy đổi về W
        # nên ta cần scale 1.0 (sau khi nhân 0.001 ra kW, ta nhân tiếp 1000 ra W → kết quả là scale 1.0)
        # Vì: P_kW = data * 0.001 -> P_W = P_kW * 1000 = data * 1.0
        "p_a":          {"address": 0x0164, "count": 2, "type": "int32", "scale": 1.0, "unit": "W"},
        "p_b":          {"address": 0x0166, "count": 2, "type": "int32", "scale": 1.0, "unit": "W"},
        "p_c":          {"address": 0x0168, "count": 2, "type": "int32", "scale": 1.0, "unit": "W"},
        "p_total":      {"address": 0x016A, "count": 2, "type": "int32", "scale": 1.0, "unit": "W"},

        # === NHÓM 6: CÔNG SUẤT PHẢN KHÁNG (int32 có dấu, scale 1.0 Var) ===
        "q_a":          {"address": 0x016C, "count": 2, "type": "int32", "scale": 1.0, "unit": "VAr"},
        "q_b":          {"address": 0x016E, "count": 2, "type": "int32", "scale": 1.0, "unit": "VAr"},
        "q_c":          {"address": 0x0170, "count": 2, "type": "int32", "scale": 1.0, "unit": "VAr"},
        "q_total":      {"address": 0x0172, "count": 2, "type": "int32", "scale": 1.0, "unit": "VAr"},

        # === NHÓM 7: CÔNG SUẤT BIỂU KIẾN (uint32 không dấu, scale 1.0 VA) ===
        "s_a":          {"address": 0x0174, "count": 2, "type": "uint32", "scale": 1.0, "unit": "VA"},
        "s_b":          {"address": 0x0176, "count": 2, "type": "uint32", "scale": 1.0, "unit": "VA"},
        "s_c":          {"address": 0x0178, "count": 2, "type": "uint32", "scale": 1.0, "unit": "VA"},
        "s_total":      {"address": 0x017A, "count": 2, "type": "uint32", "scale": 1.0, "unit": "VA"},

        # === NHÓM 8: HỆ SỐ CÔNG SUẤT (int16 có dấu, scale 0.001) ===
        "pf_a":         {"address": 0x017C, "count": 1, "type": "int16", "scale": 0.001, "unit": ""},
        "pf_b":         {"address": 0x017D, "count": 1, "type": "int16", "scale": 0.001, "unit": ""},
        "pf_c":         {"address": 0x017E, "count": 1, "type": "int16", "scale": 0.001, "unit": ""},
        "pf":           {"address": 0x017F, "count": 1, "type": "int16", "scale": 0.001, "unit": ""},

        # === NHÓM 9: TỔNG SẢN LƯỢNG LŨY KẾ (uint32, scale 0.01 kWh/kVarh) ===
        # Quy đổi đơn vị: E_kWh = data * 0.01
        "e_pt_import":  {"address": 0x000A, "count": 2, "type": "uint32", "scale": 0.01, "unit": "kWh"},
        "e_pt_export":  {"address": 0x0014, "count": 2, "type": "uint32", "scale": 0.01, "unit": "kWh"},
        "e_qt_import":  {"address": 0x0028, "count": 2, "type": "uint32", "scale": 0.01, "unit": "kVArh"},
        "e_qt_export":  {"address": 0x0032, "count": 2, "type": "uint32", "scale": 0.01, "unit": "kVArh"},
    }
