"""
backend/app.py — FastAPI Backend with WebSocket support
"""
import sys
import logging
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.logger import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List



from backend.api.config_api import router as config_router
from backend.api.scan_api import router as scan_router
from backend.api.project_api import router as project_router
from backend.api.inverter_api import router as inverter_router
from backend.api.battery_api import router as battery_router
from backend.api.auth_api import router as auth_router, get_current_user_id
from backend.api.user_api import router as user_router
from backend.api.monitoring_api import router as monitoring_router
from backend.api.comm_api import router as comm_router
from backend.api.sync_api import router as sync_router
from backend.api.schedule_api import router as schedule_router
from backend.api.account_api import router as account_router
from backend.api.meter_api import router as meter_router
from backend.api.evn_api import router as evn_router
from backend.api.network_api import router as network_router
from backend.api.zero_export_api import router as zero_export_router

from backend.core import settings as app_config

# Global instance của ZeroExportService — được inject vào API thông qua dependency
# Được set bởi run_polling.py sau khi khởi tạo, hoặc None nếu không chạy polling
ze_service_instance = None


app = FastAPI(title="Solar Datalogger Backend", version="2.0.0")

# API routes
app.include_router(auth_router)
app.include_router(config_router, prefix="/api/config", dependencies=[Depends(get_current_user_id)])
app.include_router(scan_router, prefix="/api/scan", dependencies=[Depends(get_current_user_id)])
app.include_router(project_router, prefix="/api/projects", dependencies=[Depends(get_current_user_id)])
app.include_router(inverter_router, prefix="/api/inverters", dependencies=[Depends(get_current_user_id)])
app.include_router(battery_router, prefix="/api/batteries", dependencies=[Depends(get_current_user_id)])
app.include_router(comm_router, dependencies=[Depends(get_current_user_id)])
app.include_router(user_router, dependencies=[Depends(get_current_user_id)]) 
app.include_router(monitoring_router, prefix="/api/monitoring", dependencies=[Depends(get_current_user_id)])
app.include_router(sync_router, dependencies=[Depends(get_current_user_id)])
app.include_router(schedule_router, dependencies=[Depends(get_current_user_id)])
app.include_router(account_router, prefix="/api/server-accounts", dependencies=[Depends(get_current_user_id)])
app.include_router(meter_router, prefix="/api/meters", dependencies=[Depends(get_current_user_id)])
app.include_router(evn_router, prefix="/api/evn", dependencies=[Depends(get_current_user_id)])
app.include_router(network_router, prefix="/api/network", dependencies=[Depends(get_current_user_id)])
app.include_router(zero_export_router, prefix="/api/zero-export", dependencies=[Depends(get_current_user_id)])

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.on_event("startup")
def startup_event():
    from backend.db_manager import MetadataDB, CacheDB, RealtimeDB
    from backend.services.user_service import UserService
    from backend.services.zero_export_service import ZeroExportService
    from backend.services.control_service import ControlService
    from backend.services.polling_service import PollingService
    from backend.core import settings as app_config
    
    db = MetadataDB(app_config.METADATA_DB)
    user_svc = UserService(db)
    user_svc.create_admin_if_not_exists()

    # Khởi tạo ZeroExportService ở web process để xử lý cấu hình & đồng bộ trạng thái qua SQLite CacheDB
    try:
        cache_db = CacheDB(app_config.CACHE_DB)
        realtime_db = RealtimeDB(app_config.REALTIME_DB)
        fake_polling_svc = PollingService(None, cache_db, realtime_db)
        ctrl_svc = ControlService(fake_polling_svc)
        
        global ze_service_instance
        ze_service_instance = ZeroExportService(
            cache_db=cache_db,
            metadata_db=db,
            control_service=ctrl_svc,
            polling_service=fake_polling_svc,
            schedule_service=None
        )
        logger.info("[App Startup] ZeroExportService initialized successfully on Web process.")
    except Exception as e:
        logger.error(f"[App Startup] Failed to initialize ZeroExportService: {e}", exc_info=True)
STATIC_DIR = Path(__file__).resolve().parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Datalogger API is running. Frontend not found."}

if __name__ == "__main__":
    import uvicorn
    bind_host = app_config.WEB_BIND_HOST
    public_host = app_config.WEB_PUBLIC_HOST
    port = app_config.WEB_PORT
    logger.info(
        f"Starting Solar Datalogger Backend on http://{public_host}:{port} "
        f"(bind {bind_host}:{port})"
    )
    uvicorn.run("backend.app:app", host=bind_host, port=port, reload=True)
