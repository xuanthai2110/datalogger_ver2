"""
backend/api/zero_export_api.py

REST API cho tính năng Zero Export.

Endpoints:
    GET  /api/zero-export/{project_id}          — Xem config + status
    PUT  /api/zero-export/{project_id}/config   — Cập nhật cấu hình
    POST /api/zero-export/{project_id}/enable   — Bật Zero Export
    POST /api/zero-export/{project_id}/disable  — Tắt Zero Export
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Zero Export"])

# ============================================================
# Pydantic schemas cho request/response
# ============================================================

class ZeroExportConfigRequest(BaseModel):
    """Payload để cập nhật cấu hình Zero Export."""
    meter_id: Optional[int] = Field(None, description="ID của Meter dùng làm tín hiệu PCC")
    meter_direction: Optional[str] = Field(
        None,
        description=(
            "Hướng lắp CT: "
            "GRID_SIDE (CT xuôi phía lưới), "
            "GRID_SIDE_REVERSED (CT ngược phía lưới), "
            "LOAD_SIDE (CT xuôi phía tải), "
            "LOAD_SIDE_REVERSED (CT ngược phía tải)"
        ),
    )
    export_limit_w: Optional[float] = Field(None, description="Ngưỡng xuất khẩu tối đa (W). 0 = không cho xuất")
    deadband_w: Optional[float] = Field(None, description="Vùng bất nhạy (W), tránh dao động liên tục. Mặc định 200W")
    gain: Optional[float] = Field(None, description="Hệ số khuếch đại bước điều chỉnh. Mặc định 1.0")
    ramp_kw_per_step: Optional[float] = Field(None, description="Tốc độ thay đổi setpoint tối đa (kW/chu kỳ 10s). Mặc định 50 kW")
    meter_fail_threshold: Optional[int] = Field(None, description="Số lần meter mất kết nối liên tiếp trước khi set inverter = 0 kW. Mặc định 10")


VALID_METER_DIRECTIONS = {"GRID_SIDE", "GRID_SIDE_REVERSED", "LOAD_SIDE", "LOAD_SIDE_REVERSED"}


def get_ze_service():
    """Dependency injection — lấy ZeroExportService từ app state."""
    from backend.app import ze_service_instance
    if ze_service_instance is None:
        raise HTTPException(status_code=503, detail="ZeroExportService chưa được khởi tạo")
    return ze_service_instance


@router.get("/{project_id}", summary="Xem cấu hình và trạng thái Zero Export")
def get_zero_export(project_id: int, ze_service=Depends(get_ze_service)):
    """
    Trả về cấu hình và trạng thái runtime của Zero Export cho project.

    - **suspended_by**: null = đang chạy, "EVN" = nhường EVN, "SCHEDULE" = nhường Server
    - **last_action**: INCREASE | DECREASE | HOLD | METER_FAULT | DISABLED
    - **meter_fail_count**: số lần Meter mất kết nối liên tiếp (reset khi meter khôi phục)
    """
    try:
        cfg = ze_service.get_config(project_id)
        status = ze_service.get_status(project_id)
        return {
            "config": {
                "project_id":           cfg.project_id,
                "enabled":              cfg.enabled,
                "meter_id":             cfg.meter_id,
                "meter_direction":      cfg.meter_direction,
                "export_limit_w":       cfg.export_limit_w,
                "deadband_w":           cfg.deadband_w,
                "gain":                 cfg.gain,
                "ramp_kw_per_step":     cfg.ramp_kw_per_step,
                "meter_fail_threshold": cfg.meter_fail_threshold,
            },
            "status": {
                "enabled":              status.enabled,
                "suspended_by":         status.suspended_by,
                "p_grid_w":             status.p_grid_w,
                "p_inv_total_w":        status.p_inv_total_w,
                "p_inv_setpoint_w":     status.p_inv_setpoint_w,
                "last_action":          status.last_action,
                "meter_fail_count":     status.meter_fail_count,
                "last_updated":         status.last_updated,
            },
        }
    except Exception as e:
        logger.error("[ZeroExportAPI] GET project %s error: %s", project_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{project_id}/config", summary="Cập nhật cấu hình Zero Export")
def update_zero_export_config(
    project_id: int,
    body: ZeroExportConfigRequest,
    ze_service=Depends(get_ze_service),
):
    """
    Cập nhật (partial) cấu hình Zero Export. Chỉ các trường được gửi lên mới thay đổi.

    **Lưu ý meter_direction:**
    - `GRID_SIDE`: CT đo phía lưới, chiều CT xuôi (P_meter > 0 = import từ lưới)
    - `GRID_SIDE_REVERSED`: CT đo phía lưới, chiều CT ngược
    - `LOAD_SIDE`: CT đo phía tải, chiều CT xuôi (P_meter > 0 = công suất tải)
    - `LOAD_SIDE_REVERSED`: CT đo phía tải, chiều CT ngược
    """
    try:
        # Validate meter_direction
        if body.meter_direction and body.meter_direction.upper() not in VALID_METER_DIRECTIONS:
            raise HTTPException(
                status_code=422,
                detail=f"meter_direction không hợp lệ. Chọn một trong: {VALID_METER_DIRECTIONS}",
            )

        config_dict = body.model_dump(exclude_none=True)
        if "meter_direction" in config_dict:
            config_dict["meter_direction"] = config_dict["meter_direction"].upper()

        ze_service.save_config(project_id, config_dict)
        logger.info("[ZeroExportAPI] Config updated for project %s: %s", project_id, config_dict)

        # Trả về config mới sau khi lưu
        cfg = ze_service.get_config(project_id)
        return {
            "success": True,
            "message": f"Đã cập nhật cấu hình Zero Export cho project {project_id}",
            "config": {
                "project_id":           cfg.project_id,
                "enabled":              cfg.enabled,
                "meter_id":             cfg.meter_id,
                "meter_direction":      cfg.meter_direction,
                "export_limit_w":       cfg.export_limit_w,
                "deadband_w":           cfg.deadband_w,
                "gain":                 cfg.gain,
                "ramp_kw_per_step":     cfg.ramp_kw_per_step,
                "meter_fail_threshold": cfg.meter_fail_threshold,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ZeroExportAPI] PUT config project %s error: %s", project_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/enable", summary="Bật Zero Export cho project")
def enable_zero_export(project_id: int, ze_service=Depends(get_ze_service)):
    """
    Bật Zero Export. ZE sẽ bắt đầu điều khiển từ chu kỳ tiếp theo (trong vòng 10s).

    **Yêu cầu:** Phải cấu hình `meter_id` và `meter_direction` trước khi bật.
    """
    try:
        cfg = ze_service.get_config(project_id)
        if not cfg.meter_id:
            raise HTTPException(
                status_code=400,
                detail="Chưa cấu hình meter_id. Vui lòng cấu hình Meter trước khi bật Zero Export.",
            )

        ze_service.save_config(project_id, {"enabled": True})
        logger.info("[ZeroExportAPI] Zero Export ENABLED for project %s", project_id)
        return {
            "success": True,
            "message": f"Zero Export đã được BẬT cho project {project_id}. Chu kỳ điều khiển tiếp theo sẽ bắt đầu trong vòng 10s.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ZeroExportAPI] Enable project %s error: %s", project_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/disable", summary="Tắt Zero Export cho project")
def disable_zero_export(project_id: int, ze_service=Depends(get_ze_service)):
    """
    Tắt Zero Export vĩnh viễn cho đến khi user bật lại qua API.

    Khi tắt, Inverter KHÔNG được reset về 100% tự động — giữ nguyên setpoint cuối cùng.
    Để reset Inverter, dùng endpoint `/api/schedule/reset`.
    """
    try:
        ze_service.save_config(project_id, {"enabled": False})
        logger.info("[ZeroExportAPI] Zero Export DISABLED for project %s", project_id)
        return {
            "success": True,
            "message": (
                f"Zero Export đã được TẮT cho project {project_id}. "
                "Inverter giữ nguyên setpoint cuối cùng."
            ),
        }
    except Exception as e:
        logger.error("[ZeroExportAPI] Disable project %s error: %s", project_id, e)
        raise HTTPException(status_code=500, detail=str(e))
