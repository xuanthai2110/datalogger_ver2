from fastapi import APIRouter, Depends, HTTPException
from backend.services.monitoring_service import MonitoringService
from backend.core import settings as app_config
import logging
from backend.api.auth_api import get_current_user_id

def get_monitoring_service() -> MonitoringService:
    from backend.db_manager import MetadataDB, RealtimeDB, CacheDB
    return MonitoringService(
        metadata_db=MetadataDB(app_config.METADATA_DB),
        realtime_db=RealtimeDB(app_config.REALTIME_DB),
        cache_db=CacheDB(app_config.CACHE_DB)
    )

router = APIRouter(tags=["monitoring"])
logger = logging.getLogger(__name__)

@router.get("/project/{project_id}/latest")
def get_latest_project_data(project_id: int, svc: MonitoringService = Depends(get_monitoring_service), current_user = Depends(get_current_user_id)):
    """Lấy dữ liệu realtime mới nhất của một dự án (ưu tiên RAM)."""
    try:
        data = svc.get_latest_project_data(project_id)
        if not data:
            return {"ok": False, "message": "No data found"}
        return data
    except Exception as e:
        logger.error(f"get_latest_project_data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/inverter/{inverter_id}/latest")
def get_latest_inverter_data(inverter_id: int, svc: MonitoringService = Depends(get_monitoring_service), current_user = Depends(get_current_user_id)):
    """Lấy dữ liệu realtime 10s từ RAM."""
    try:
        data = svc.get_latest_inverter_data(inverter_id)
        if not data:
            return {"ok": False, "message": "No data found in cache"}
        return data
    except Exception as e:
        logger.error(f"get_latest_inverter_data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/inverter/{inverter_id}/detail")
def get_inverter_detail(inverter_id: int, svc: MonitoringService = Depends(get_monitoring_service), current_user = Depends(get_current_user_id)):
    """Lấy toàn bộ dữ liệu realtime chi tiết (AC, MPPT, String, Errors) của một biến tần."""
    try:
        return svc.get_inverter_detail(inverter_id)
    except Exception as e:
        logger.error(f"get_inverter_detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/summary")
def get_dashboard_summary(svc: MonitoringService = Depends(get_monitoring_service), current_user = Depends(get_current_user_id)):
    """Lấy tóm tắt dữ liệu cho dashboard."""
    try:
        return svc.get_dashboard_summary()
    except Exception as e:
        logger.error(f"get_dashboard_summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/power-flow")
def get_power_flow_data(project_id: int = None, svc: MonitoringService = Depends(get_monitoring_service), current_user = Depends(get_current_user_id)):
    """Lấy dữ liệu sơ đồ dòng công suất Power Flow realtime."""
    try:
        return svc.get_power_flow(project_id)
    except Exception as e:
        logger.error(f"get_power_flow_data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/project/{project_id}/range")
def get_project_history(project_id: int, start: str, end: str, svc: MonitoringService = Depends(get_monitoring_service), current_user = Depends(get_current_user_id)):
    """Lấy dữ liệu lịch sử của dự án trong khoảng thời gian (start/end format YYYY-MM-DD HH:MM:SS)."""
    try:
        return svc.get_project_history(project_id, start, end)
    except Exception as e:
        logger.error(f"get_project_history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/inverter/{inverter_id}/range")
def get_inverter_history(inverter_id: int, start: str, end: str, svc: MonitoringService = Depends(get_monitoring_service), current_user = Depends(get_current_user_id)):
    """Lấy dữ liệu lịch sử AC của biến tần trong khoảng thời gian."""
    try:
        return svc.get_inverter_history(inverter_id, start, end)
    except Exception as e:
        logger.error(f"get_inverter_history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
