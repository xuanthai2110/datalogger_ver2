# services/normalization_service.py
"""
NormalizationService - Chuẩn hoá và kiểm tra dữ liệu đọc từ inverter.

Nhiệm vụ:
  1. Chuẩn hoá: Làm tròn, đổi đơn vị (W -> kW), gán None cho
     các giá trị không hợp lệ.
  2. Kiểm tra khoảng hợp lệ (validation range): Các giá trị nằm
     ngoài khoảng vật lý cho phép sẽ bị thay thế bằng None và
     ghi log cảnh báo.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# =========================================================
# ====== KHOẢNG GIÁ TRỊ HỢP LỆ CHO TỪNG THAM SỐ =========
# =========================================================
# Đơn vị: giống với đơn vị sau khi scale từ driver
#   V       -> V
#   I       -> A
#   P_ac    -> kW  (driver đã scale W -> kW)
#   Q_ac    -> kvar
#   PF      -> -1.0 .. 1.0
#   Hz      -> Hz
#   Temp_C  -> °C
#   IR      -> kΩ
#   E_daily -> kWh
#   E_total -> kWh
#   mppt_voltage -> V
#   mppt_current -> A
#   string_current -> A
#   p_dc_w  -> kW

VALID_RANGE: dict[str, tuple[float, float]] = {
    # AC
    "v_a":        (0.0,    440.0),
    "v_b":        (0.0,    440.0),
    "v_c":        (0.0,    440.0),
    "i_a":        (-1000.0, 1000.0),
    "i_b":        (-1000.0, 1000.0),
    "i_c":        (-1000.0, 1000.0),
    "p_inv_w":    (-200000.0,  200000.0),    # W
    "q_inv_var":  (-200000.0,  200000.0),    # var
    "pf":         (-1.0,    1.0),
    "grid_hz":    (0.0,    70.0),

    # DC
    "p_dc_w":     (0.0,    400000.0),     # W
    **{f"mppt_{i}_voltage": (-1000.0, 1500.0) for i in range(1, 11)},
    **{f"mppt_{i}_current": (-100.0, 100.0)  for i in range(1, 11)},
    **{f"string_{i}_current": (-100.0, 100.0) for i in range(1, 21)},

    # Stat
    "temp_c":   (-40.0,  100.0),
    "ir":       (0.0,    1000000.0),  # kΩ
    "e_daily":  (0.0,    10000.0),  # kWh
    "e_monthly": (0.0,   1000000.0), # kWh
    "e_total":  (0.0,    1e9),      # kWh

    # Battery (Hybrid Inverter & BMS)
    "inv_batt_u":               (0.0,    1000.0),
    "inv_batt_i":               (-500.0,  500.0),
    "inv_batt_p":               (-200000.0, 200000.0),
    "bms_batt_u":               (0.0,    1000.0),
    "bms_batt_i":               (-500.0,  500.0),
    "bms_batt_p":               (-200000.0, 200000.0),
    "bms_batt_soc":             (0.0,    100.0),
    "bms_batt_soh":             (0.0,    100.0),
    "bms_max_charge_i":         (0.0,    500.0),
    "bms_max_discharge_i":      (0.0,    500.0),
    "bms_discharge_volt_limit": (0.0,    1000.0),
    "bms_min_cell_volt":        (0.0,    10.0),
    "bms_max_cell_volt":        (0.0,    10.0),
    "bms_min_cell_temp":        (-40.0,  100.0),
    "bms_max_cell_temp":        (-40.0,  100.0),
    "e_charge_daily":           (0.0,    10000.0),
    "e_discharge_daily":        (0.0,    10000.0),
    "e_charge_total":           (0.0,    1e9),
    "e_discharge_total":        (0.0,    1e9),

    # Load & Backup Port (Hybrid Inverter)
    "p_load_w":                 (0.0,    200000.0),
    "e_load_daily":             (0.0,    10000.0),
    "e_load_total":             (0.0,    1e9),
    "u_backup_a":               (0.0,    440.0),
    "u_backup_b":               (0.0,    440.0),
    "u_backup_c":               (0.0,    440.0),
    "i_backup_a":               (0.0,    500.0),
    "i_backup_b":               (0.0,    500.0),
    "i_backup_c":               (0.0,    500.0),
    "p_backup_a":               (0.0,    200000.0),
    "p_backup_b":               (0.0,    200000.0),
    "p_backup_c":               (0.0,    200000.0),
    "s_backup_load":            (0.0,    200000.0),
    "e_backup_daily":           (0.0,    10000.0),
    "e_backup_total":           (0.0,    1e9),

    # Telemetry Final Payload Keys
    "Temp_C": (-40.0, 100.0), "P_ac": (-200000.0, 200000.0), "P_dc": (0.0, 400000.0),
    "E_daily": (0.0, 10000.0), "E_monthly": (0.0, 1000000.0), "E_total": (0.0, 1e9),
    "IR": (0.0, 10000.0), "Q_ac": (-200000.0, 200000.0), "V_a": (0.0, 440.0),
    "V_b": (0.0, 440.0), "V_c": (0.0, 440.0), "I_a": (-1000.0, 1000.0),
    "I_b": (-1000.0, 1000.0), "I_c": (-1000.0, 1000.0), "PF": (-1.0, 1.0),
    "H": (0.0, 70.0), "V_mppt": (0.0, 1500.0), "I_mppt": (-100.0, 100.0),
    "P_mppt": (0.0, 200000.0), "Max_I": (-100.0, 100.0), "Max_V": (0.0, 1500.0),
    "Max_P": (0.0, 200000.0)
}

# =========================================================
# ====== ĐỊNH NGHĨA LÀM TRÒN ==============================
# =========================================================
ROUND_DIGITS: dict[str, int] = {
    "v_a": 2, "v_b": 2, "v_c": 2,
    "i_a": 2, "i_b": 2, "i_c": 2,
    "p_inv_w": 2, "q_inv_var": 2, "pf": 2,
    "grid_hz": 2, "p_dc_w": 2,
    "temp_c": 2, "e_daily": 2, "e_monthly": 2, "e_total": 2,
    "inv_batt_u": 2, "inv_batt_i": 2, "inv_batt_p": 2,
    "bms_batt_u": 2, "bms_batt_i": 2, "bms_batt_p": 2,
    "bms_batt_soc": 1, "bms_batt_soh": 1,
    "e_charge_daily": 2, "e_discharge_daily": 2,
    "e_charge_total": 2, "e_discharge_total": 2,
    "bms_min_cell_temp": 2, "bms_max_cell_temp": 2,
    "bms_min_cell_volt": 3, "bms_max_cell_volt": 3,
    "p_load_w": 2, "e_load_daily": 2, "e_load_total": 2,
    "u_backup_a": 2, "u_backup_b": 2, "u_backup_c": 2,
    "i_backup_a": 2, "i_backup_b": 2, "i_backup_c": 2,
    "p_backup_a": 2, "p_backup_b": 2, "p_backup_c": 2,
    "s_backup_load": 2, "e_backup_daily": 2, "e_backup_total": 2,
    **{f"mppt_{i}_voltage": 2 for i in range(1, 11)},
    **{f"mppt_{i}_current": 2 for i in range(1, 11)},
    **{f"string_{i}_current": 2 for i in range(1, 21)},

    # Telemetry Final Payload Keys
    "Temp_C": 2, "P_ac": 2, "P_dc": 2, "E_daily": 2, "E_monthly": 2, "E_total": 2,
    "IR": 2, "Q_ac": 2, "V_a": 2, "V_b": 2, "V_c": 2, "I_a": 2, "I_b": 2, "I_c": 2,
    "PF": 2, "H": 2, "V_mppt": 2, "I_mppt": 2, "P_mppt": 2, "Max_I": 2, "Max_V": 2,
    "Max_P": 2
}

DEFAULT_ROUND = 2  # Mặc định làm tròn 2 chữ số thập phân cho các tham số chưa khai báo


class NormalizationService:
    """
    Chuẩn hoá và kiểm tra dữ liệu trả về từ driver.

    Sử dụng:
        svc = NormalizationService()
        clean = svc.normalize(raw_data)
    """

    def __init__(self, strict: bool = False):
        """
        strict=True  -> raise ValueError nếu gặp giá trị ngoài khoảng.
        strict=False -> gán None và log cảnh báo (mặc định).
        """
        self.strict = strict
        # Bộ đếm số lần giảm e_total liên tiếp để nhận diện Reset/Thay thế thiết bị
        self._reset_counters: dict[str, int] = {}

    # ----------------------------------------------------------
    def normalize(self, data: dict, last_data: dict = None, device_id: Any = "default") -> dict:
        """
        Chuẩn hoá toàn bộ dict dữ liệu từ driver.
        Trả về dict mới đã được làm sạch.
        """
        result = {}
        for key, raw_value in data.items():
            result[key] = self._process_field(key, raw_value)

        # 1. Lọc trôi điểm không ban đêm (Zero-drift Filter) - Không cần dữ liệu lịch sử
        p_dc = result.get("p_dc_w")
        p_ac = result.get("p_inv_w")
        ir = result.get("ir")
        
        # Nhận diện ban đêm theo thứ tự ưu tiên:
        # 1. Nếu có công suất DC thực tế -> dùng nó làm chuẩn (p_dc_w <= 10W là ban đêm)
        # 2. Nếu không có DC nhưng có AC  -> dùng AC (p_inv_w <= 20W là ban đêm)
        # 3. Chỉ dùng ir == 0.0 làm dự phòng khi không có cả hai thông số công suất trên
        if p_dc is not None:
            is_night = p_dc <= 10.0
        elif p_ac is not None:
            is_night = p_ac <= 20.0
        else:
            is_night = (ir == 0.0) if ir is not None else False
            
        if is_night:
            if "p_inv_w" in result: result["p_inv_w"] = 0.0
            if "p_dc_w" in result: result["p_dc_w"] = 0.0
            for i in range(1, 11):
                if f"mppt_{i}_current" in result: result[f"mppt_{i}_current"] = 0.0
            for i in range(1, 21):
                if f"string_{i}_current" in result: result[f"string_{i}_current"] = 0.0
            for phase in ["a", "b", "c"]:
                if f"i_{phase}" in result: result[f"i_{phase}"] = 0.0

        # Nếu không có dữ liệu lịch sử (last_data), trả về kết quả
        if not last_data:
            return result

        # 2. Lọc đơn điệu cho e_total (Tổng sản lượng điện)
        last_e_total = last_data.get("e_total") or last_data.get("E_total")
        new_e_total = result.get("e_total")
        
        if last_e_total is not None and new_e_total is not None:
            last_e_total_val = float(last_e_total)
            if new_e_total < last_e_total_val:
                # Nếu giá trị mới rất nhỏ (< 10 kWh), có thể là reset inverter/thay máy mới
                if new_e_total < 10.0:
                    counter_key = f"{device_id}_e_total_reset"
                    self._reset_counters[counter_key] = self._reset_counters.get(counter_key, 0) + 1
                    # Nếu duy trì mức cực nhỏ này liên tiếp 5 lần -> Chấp nhận reset thiết bị
                    if self._reset_counters[counter_key] >= 5:
                        logger.info(f"[Norm] Device {device_id} e_total reset detected & accepted: {new_e_total} kWh")
                        self._reset_counters[counter_key] = 0
                    else:
                        # Tạm thời giữ nguyên giá trị cũ để chờ xác nhận ổn định
                        result["e_total"] = last_e_total_val
                else:
                    logger.warning(f"[Norm] e_total decreased from {last_e_total_val} to {new_e_total}. Keeping last value.")
                    result["e_total"] = last_e_total_val
            else:
                # Reset bộ đếm nếu giá trị hoạt động bình thường trở lại
                self._reset_counters[f"{device_id}_e_total_reset"] = 0
                
        # Lọc đơn điệu cho e_daily (Sản lượng ngày)
        last_e_daily = last_data.get("e_daily") or last_data.get("E_daily")
        new_e_daily = result.get("e_daily")
        if last_e_daily is not None and new_e_daily is not None:
            last_e_daily_val = float(last_e_daily)
            # Chỉ lọc khi chưa qua ngày mới (giá trị cũ lớn hơn 0 và giá trị mới bị sụt giảm bất thường)
            if 0.0 < new_e_daily < last_e_daily_val:
                logger.warning(f"[Norm] e_daily decreased from {last_e_daily_val} to {new_e_daily}. Keeping last value.")
                result["e_daily"] = last_e_daily_val

        # Lọc nhiễu nhảy vọt điện áp lưới (Voltage Spike Filter)
        for phase in ["a", "b", "c"]:
            key = f"v_{phase}"
            last_v = last_data.get(key) or last_data.get(key.capitalize())
            new_v = result.get(key)
            if last_v is not None and new_v is not None:
                last_v_val = float(last_v)
                # Nếu lệch quá 50V và không phải là trường hợp mất lưới hoàn toàn (về 0V) hoặc bắt đầu khởi động từ 0V
                if abs(new_v - last_v_val) > 50.0 and new_v > 10.0 and last_v_val > 10.0:
                    logger.warning(f"[Norm] Voltage spike detected on {key}: {last_v_val} -> {new_v}. Keeping last value.")
                    result[key] = last_v_val

        return result

    # ----------------------------------------------------------
    def _process_field(self, key: str, value: Any) -> Any:
        """Xử lý một trường: kiểm tra None, kiểu số, khoảng hợp lệ, làm tròn."""

        # 1. Giữ nguyên các trường không phải số (string, bool, dict, list, None)
        if value is None:
            return None
        if isinstance(value, (str, bool, dict, list)):
            return value

        # 2. Ép về float
        try:
            value = float(value)
        except (TypeError, ValueError):
            logger.warning(f"[Norm] {key}: cannot convert '{value}' to float -> None")
            return None

        # 3. Xử lý noise và reverse polarity cho DC side (MPPT, String)
        if "mppt_" in key or "string_" in key:
            if -1.0 <= value < 0.0:
                # Giá trị rác, cho về 0
                return 0.0
            # Nếu value < -1.0, chúng ta giữ nguyên giá trị âm để TrackingService phát hiện reverse polarity

        # 4. Kiểm tra khoảng hợp lệ
        if key in VALID_RANGE:
            lo, hi = VALID_RANGE[key]
            if not (lo <= value <= hi):
                msg = f"[Norm] {key}={value} out of range [{lo}, {hi}]"
                if self.strict:
                    raise ValueError(msg)
                logger.warning(msg + " -> None")
                return None

        # 5. Làm tròn 2 chữ số thập phân (dùng bảng ROUND_DIGITS nếu có, fallback DEFAULT_ROUND)
        digits = ROUND_DIGITS.get(key, DEFAULT_ROUND)
        value = round(value, digits)

        return value

    # ----------------------------------------------------------
    def validate_snapshot(self, data: dict) -> dict[str, list[str]]:
        """
        Kiểm tra toàn bộ snapshot và trả về dict các cảnh báo theo từng key.
        Dùng để log / debug mà không thay đổi dữ liệu gốc.

        Trả về: {"v_a": ["out of range: 500.0 > 440.0"], ...}
        """
        warnings: dict[str, list[str]] = {}
        for key, value in data.items():
            if value is None or not isinstance(value, (int, float)):
                continue
            if key in VALID_RANGE:
                lo, hi = VALID_RANGE[key]
                if not (lo <= float(value) <= hi):
                    warnings.setdefault(key, []).append(
                        f"out of range: {value} not in [{lo}, {hi}]"
                    )
        return warnings
