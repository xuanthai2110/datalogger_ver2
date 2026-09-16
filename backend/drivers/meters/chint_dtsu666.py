"""
backend/drivers/chint_dtsu666.py — Driver cho Meter Chint DTSU666.
Hỗ trợ đọc dữ liệu tức thời và năng lượng tích lũy qua Modbus RTU/TCP.
"""

import logging
from typing import Dict, Any, Optional
from backend.drivers.meters.meter_base import MeterDriverBase

logger = logging.getLogger(__name__)


class MeterChintdtsu666(MeterDriverBase):
    """
    Driver cho Chint DTSU666 (3 pha).
    Sử dụng Function Code 03 (Holding Registers).
    Xử lý đặc biệt cho Năng lượng phản kháng (tính từ 4 góc phần tư).
    """

    # DTSU666 sử dụng FC03 cho các vùng địa chỉ này
    read_function = "holding"

    register_map: Dict[str, Dict[str, Any]] = {
        # === NHÓM 1: THÔNG SỐ CÀI ĐẶT ===
        "soft_version": {"address": 0,    "count": 1, "type": "int16", "unit": ""},
        "net_type":     {"address": 3,    "count": 1, "type": "int16", "unit": "0:3P4W, 1:3P3W"},
        "ct_rate":      {"address": 6,    "count": 1, "type": "int16", "unit": "CT"},
        "vt_rate":      {"address": 7,    "count": 1, "type": "int16", "scale": 0.1, "unit": "VT"},
        "modbus_addr":  {"address": 45,   "count": 1, "type": "int16", "unit": ""},
        "baudrate_id":  {"address": 46,   "count": 1, "type": "int16", "unit": "0:1200..3:9600"},

        # === NHÓM 2: DỮ LIỆU ĐIỆN (Floating - Cần Scale) ===
        "v_ab":         {"address": 8192, "count": 2, "type": "float32", "scale": 0.1, "unit": "V"},
        "v_bc":         {"address": 8194, "count": 2, "type": "float32", "scale": 0.1, "unit": "V"},
        "v_ca":         {"address": 8196, "count": 2, "type": "float32", "scale": 0.1, "unit": "V"},
        "v_a":          {"address": 8198, "count": 2, "type": "float32", "scale": 0.1, "unit": "V"},
        "v_b":          {"address": 8200, "count": 2, "type": "float32", "scale": 0.1, "unit": "V"},
        "v_c":          {"address": 8202, "count": 2, "type": "float32", "scale": 0.1, "unit": "V"},

        "i_a":          {"address": 8204, "count": 2, "type": "float32", "scale": 0.001, "unit": "A"},
        "i_b":          {"address": 8206, "count": 2, "type": "float32", "scale": 0.001, "unit": "A"},
        "i_c":          {"address": 8208, "count": 2, "type": "float32", "scale": 0.001, "unit": "A"},

        # Công suất (P/Q) dùng scale 0.1 theo đơn vị W/var
        "p_total":      {"address": 8210, "count": 2, "type": "float32", "scale": 0.1, "unit": "W"},
        "p_a":          {"address": 8212, "count": 2, "type": "float32", "scale": 0.1, "unit": "W"},
        "p_b":          {"address": 8214, "count": 2, "type": "float32", "scale": 0.1, "unit": "W"},
        "p_c":          {"address": 8216, "count": 2, "type": "float32", "scale": 0.1, "unit": "W"},

        "q_total":      {"address": 8218, "count": 2, "type": "float32", "scale": 0.1, "unit": "VAr"},
        "q_a":          {"address": 8220, "count": 2, "type": "float32", "scale": 0.1, "unit": "VAr"},
        "q_b":          {"address": 8222, "count": 2, "type": "float32", "scale": 0.1, "unit": "VAr"},
        "q_c":          {"address": 8224, "count": 2, "type": "float32", "scale": 0.1, "unit": "VAr"},

        "pf":           {"address": 8234, "count": 2, "type": "float32", "scale": 0.001, "unit": ""},
        "pf_a":         {"address": 8236, "count": 2, "type": "float32", "scale": 0.001, "unit": ""},
        "pf_b":         {"address": 8238, "count": 2, "type": "float32", "scale": 0.001, "unit": ""},
        "pf_c":         {"address": 8240, "count": 2, "type": "float32", "scale": 0.001, "unit": ""},
        "f":            {"address": 8260, "count": 2, "type": "float32", "scale": 0.01, "unit": "Hz"},

        # === NHÓM 3: DỮ LIỆU NĂNG LƯỢNG (401EH - 4050H) ===
        "e_pt_import":  {"address": 16414, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"}, # ImpEp (current positive active total)
        "e_pt_export":  {"address": 16424, "count": 2, "type": "float32", "scale": 1.0, "unit": "kWh"}, # ExpEp (current negative active total)
        "q1":           {"address": 16434, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVarh"}, # Q1Eq
        "q2":           {"address": 16444, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVarh"}, # Q2Eq
        "q3":           {"address": 16454, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVarh"}, # Q3Eq
        "q4":           {"address": 16464, "count": 2, "type": "float32", "scale": 1.0, "unit": "kVarh"}, # Q4Eq
    }

    def read_all(self) -> Optional[Dict[str, float]]:
        """
        Đọc dữ liệu và thực hiện tính toán bổ sung.
        """
        # 1. Sử dụng logic đọc và tính toán ảo của MeterDriverBase
        data = super().read_all()
        if not data:
            return None

        # 2. Quy đổi Năng lượng phản kháng từ 4 góc phần tư
        # Import = Q1 (Cảm kháng thu) + Q4 (Dung kháng thu)
        data["e_qt_import"] = round(data.get("q1", 0.0) + data.get("q4", 0.0), 4)
        
        # Export = Q2 (Dung kháng phát) + Q3 (Cảm kháng phát)
        data["e_qt_export"] = round(data.get("q2", 0.0) + data.get("q3", 0.0), 4)

        return data

# Class alias cho tương thích đặt tên khác hoa/thường
MeterChintDtsu666 = MeterChintdtsu666
