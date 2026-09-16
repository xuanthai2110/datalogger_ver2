from dataclasses import dataclass
from typing import Optional


# =========================
# CONFIG
# =========================
@dataclass
class ZeroExportConfig:
    """Cấu hình Zero Export cho từng project."""
    project_id: int
    enabled: bool = False

    # Meter signal
    meter_id: Optional[int] = None
    meter_direction: str = "GRID_SIDE"
    # Hướng CT:
    #   GRID_SIDE          - CT đo phía lưới, CT xuôi  (P_meter > 0 = import từ lưới)
    #   GRID_SIDE_REVERSED - CT đo phía lưới, CT ngược (P_meter > 0 = export ra lưới)
    #   LOAD_SIDE          - CT đo phía tải,  CT xuôi  (P_meter > 0 = công suất tải)
    #   LOAD_SIDE_REVERSED - CT đo phía tải,  CT ngược (P_meter < 0 = công suất tải)

    # Control parameters
    export_limit_w: float = 0.0       # Ngưỡng xuất khẩu tối đa (W). 0 = không cho xuất
    deadband_w: float = 200.0         # Vùng bất nhạy (W), tránh dao động liên tục
    gain: float = 1.0                 # Hệ số khuếch đại bước điều chỉnh
    ramp_kw_per_step: float = 50.0    # Tốc độ thay đổi tối đa (kW/bước 10s)

    # Fault thresholds
    meter_fail_threshold: int = 10    # Số lần thất bại liên tiếp → báo METER_FAULT + set 0 kW


# =========================
# STATUS (Runtime)
# =========================
@dataclass
class ZeroExportStatus:
    """Trạng thái Zero Export tại runtime — không lưu DB."""
    project_id: int
    enabled: bool

    suspended_by: Optional[str] = None       # None | "EVN" | "SCHEDULE"
    p_grid_w: Optional[float] = None         # Công suất lưới đo được (W, dương = import)
    p_inv_total_w: Optional[float] = None    # Tổng công suất inverter hiện tại (W)
    p_inv_setpoint_w: Optional[float] = None # Setpoint cuối cùng ghi xuống inverter (W)
    last_action: Optional[str] = None        # "INCREASE" | "DECREASE" | "HOLD" | "FALLBACK" | "METER_FAULT"
    meter_fail_count: int = 0                # Số lần meter thất bại liên tiếp
    last_updated: Optional[str] = None
