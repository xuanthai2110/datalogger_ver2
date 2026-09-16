"""
web/routes/scan_route.py — POST /api/scan
Refactored to support background scanning and cancellation.
"""
from fastapi import APIRouter, Body, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from typing import Optional
from backend.services.setup_service import SetupService
from dataclasses import asdict
from backend.models.inverter import InverterCreate
import logging
import time
import threading
import os
import importlib
from backend.core import settings as app_config

def get_project_service():
    from backend.db_manager import MetadataDB, RealtimeDB
    from backend.services.project_service import ProjectService
    return ProjectService(MetadataDB(app_config.METADATA_DB), RealtimeDB(app_config.REALTIME_DB))

router = APIRouter(tags=["scan"])
logger = logging.getLogger(__name__)

def _get_driver_filename(brand: str, model: str) -> str:
    clean_model = model.lower().replace("-", "_").replace(".", "_")
    return f"{brand.lower()}_{clean_model}.py"

def _find_comm_id(comm: dict) -> Optional[int]:
    from typing import Optional
    comm_id = comm.get("id")
    if comm_id:
        return int(comm_id)
    try:
        from backend.db_manager import MetadataDB
        db = MetadataDB(app_config.METADATA_DB)
        comms = db.get_comm_config()
        for c in comms:
            if c.comm_type == comm.get("comm_type"):
                if c.comm_type == "TCP":
                    if c.host == comm.get("host") and int(c.port) == int(comm.get("port", 502)):
                        return c.id
                else:
                    if c.com_port and comm.get("com_port") and c.com_port.strip() == comm.get("com_port").strip():
                        return c.id
    except Exception as e:
        logger.error(f"[Scan] Fallback comm lookup failed: {e}")
    return None

def normalize_type_code(tc):
    if tc is None:
        return set()
    if isinstance(tc, int):
        return {tc}
    if isinstance(tc, set):
        return tc
    if isinstance(tc, list):
        res = set()
        for x in tc:
            res.update(normalize_type_code(x))
        return res
    if isinstance(tc, str):
        tc = tc.strip()
        if "," in tc:
            res = set()
            for part in tc.split(","):
                res.update(normalize_type_code(part.strip()))
            return res
        if tc.lower().startswith("0x"):
            try:
                return {int(tc, 16)}
            except:
                pass
        else:
            try:
                return {int(tc)}
            except:
                pass
        return {tc}
    return {tc}

@router.get("/models")
def get_models():
    try:
        from backend.services.detect_service import SUNGROW_MODEL, HUAWEI_MODEL, SOLIS_MODEL
        drivers_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "drivers")
        existing_files = set(os.listdir(drivers_dir))

        valid_sungrow = [m["model"] for m in SUNGROW_MODEL if _get_driver_filename("Sungrow", m["model"]) in existing_files]
        valid_huawei = [m["model"] for m in HUAWEI_MODEL if _get_driver_filename("Huawei", m["model"]) in existing_files]
        valid_solis = [m["model"] for m in SOLIS_MODEL]

        return {
            "Sungrow": sorted(list(set(valid_sungrow))),
            "Huawei": sorted(list(set(valid_huawei))),
            "GoodWe": ["GW80KMT"],
            "Solis": sorted(list(set(valid_solis)))
        }
    except Exception as e:
        logger.error(f"[scan/models] Error: {e}")
        return {"Sungrow": [], "Huawei": [], "GoodWe": [], "Solis": []}


# Global state for scanning
class ScanState:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.progress = 0  # Current Slave ID
        self.total = 0     # End Slave ID
        self.results = []
        self.error = None
        self.lock = threading.Lock()

scan_state = ScanState()
meter_scan_state = ScanState()

# ... (Existing inverter scan functions) ...

def background_meter_scan(comm: dict):
    global meter_scan_state
    
    brand = comm.get("brand")
    model = comm.get("model")
    slave_start = int(comm.get("slave_id_start", 1))
    slave_end = int(comm.get("slave_id_end", 30))
    comm_id = _find_comm_id(comm)
    
    if comm_id:
        try:
            from backend.db_manager import MetadataDB
            db = MetadataDB(app_config.METADATA_DB)
            db.set_setting(f"scanning_comm_{comm_id}", "true")
        except Exception as e:
            logger.error(f"[MeterScan] Failed to set scanning status for comm {comm_id}: {e}")
    
    with meter_scan_state.lock:
        meter_scan_state.is_running = True
        meter_scan_state.stop_requested = False
        meter_scan_state.progress = slave_start
        meter_scan_state.total = slave_end
        meter_scan_state.results = []
        meter_scan_state.error = None

    transport = None
    try:
        from backend.services.polling_service import PollingService
        from backend.db_manager import MetadataDB, RealtimeDB, CacheDB
        from backend.services.project_service import ProjectService
        
        # Cần một polling service tạm thời để thực hiện quét thiết bị
        m_db = MetadataDB(app_config.METADATA_DB)
        r_db = RealtimeDB(app_config.REALTIME_DB)
        c_db = CacheDB(app_config.CACHE_DB)
        p_svc = ProjectService(m_db, r_db)
        
        ps = PollingService(p_svc, c_db, r_db)
        
        transport = _get_transport(comm)
        
        for slave_id in range(slave_start, slave_end + 1):
            with meter_scan_state.lock:
                if meter_scan_state.stop_requested: break
                meter_scan_state.progress = slave_id

            try:
                # Dùng logic scan_meters đã viết trong PollingService
                driver = ps._get_meter_driver(brand, transport, slave_id, model)
                if driver:
                    data = driver.read_all()
                    if data:
                        sn = driver.read_serial_number()
                        res = {
                            "brand": brand,
                            "model": model,
                            "slave_id": slave_id,
                            "serial_number": sn,
                            "v_a": data.get("v_a"),
                            "p_total": data.get("p_total")
                        }
                        with meter_scan_state.lock:
                            meter_scan_state.results.append(res)
            except Exception as e:
                logger.debug(f"[MeterScan] Error at sid {slave_id}: {e}")

    except Exception as e:
        logger.error(f"[MeterScan] Critical error: {e}")
        with meter_scan_state.lock:
            meter_scan_state.error = str(e)
    finally:
        if transport: transport.close()
        with meter_scan_state.lock:
            meter_scan_state.is_running = False
        if comm_id:
            try:
                from backend.db_manager import MetadataDB
                db = MetadataDB(app_config.METADATA_DB)
                db.set_setting(f"scanning_comm_{comm_id}", "false")
            except Exception as e:
                logger.error(f"[MeterScan] Failed to clear scanning status for comm {comm_id}: {e}")

@router.get("/meters/models")
def get_meter_models():
    # Danh sách các meter driver hiện có
    return {
        "Chint": ["DTSU666"],
        "Acrel": ["DTSD1352"] # Ví dụ
    }

@router.post("/meters/start")
def start_meter_scan(background_tasks: BackgroundTasks, body: dict = Body(...)):
    global meter_scan_state
    with meter_scan_state.lock:
        if meter_scan_state.is_running:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Meter scan already running"})
    
    comm = body.get("comm", {})
    background_tasks.add_task(background_meter_scan, comm)
    return {"ok": True, "message": "Meter scan started"}

@router.get("/meters/status")
def get_meter_scan_status():
    with meter_scan_state.lock:
        return {
            "is_running": meter_scan_state.is_running,
            "progress": meter_scan_state.progress,
            "total": meter_scan_state.total,
            "results": meter_scan_state.results,
            "error": meter_scan_state.error
        }

@router.post("/meters/stop")
def stop_meter_scan():
    with meter_scan_state.lock:
        meter_scan_state.stop_requested = True
    return {"ok": True}

@router.post("/meters/save")
def save_meters(body: dict = Body(...)):
    from backend.models.meter import MeterCreate
    svc = get_project_service()
    meters_in = body.get("meters", [])
    project_id = body.get("project_id")
    if not project_id:
        return JSONResponse(status_code=400, content={"ok": False, "error": "project_id is required"})
        
    saved = 0
    for m in meters_in:
        m["project_id"] = project_id
        # Nếu không có serial_number (read_serial_number trả về None), user phải nhập tay từ frontend
        # Ở đây ta giả định data đã hợp lệ
        svc.create_meter(MeterCreate(**m))
        saved += 1
    return {"ok": True, "saved": saved}

def _get_driver_class(driver_name: str, brand: str = None, model: str = None):
    if brand and model:
        if brand.lower() == "solis":
            if "s6" in model.lower() or "eh3p99" in model.lower():
                from backend.drivers.inverters.solis_S6_EH3P99_9K10_NV_YD_H import SolisS6HybridDriver
                return SolisS6HybridDriver
            elif "110k" in model.lower():
                from backend.drivers.inverters.solis_110k import Solis110k
                return Solis110k
            elif "100k" in model.lower():
                from backend.drivers.inverters.solis_100k import Solis100k
                return Solis100k
        # Dynamic import: try subfolder inverters first
        clean_model_mod = model.lower().replace("-", "_").replace(".", "_")
        clean_model_class = model.replace("-", "").replace(".", "").lower()
        class_name = f"{brand.capitalize()}{clean_model_class}"
        
        module_names = [
            f"backend.drivers.inverters.{brand.lower()}_{clean_model_mod}",
            f"backend.drivers.{brand.lower()}_{clean_model_mod}"
        ]
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
                return getattr(module, class_name)
            except Exception:
                continue

        logger.error(f"Cannot load dynamic driver class {class_name} for {brand} {model}")
        raise ValueError(f"Driver logic class not found for {brand} {model}")

    # Fallback to old behavior
    if driver_name == "Huawei":
        from backend.drivers.inverters.huawei_sun2000_110ktl import Huaweisun2000110ktl
        return Huaweisun2000110ktl
    elif driver_name == "Sungrow":
        from backend.drivers.inverters.sungrow_sg110cx import Sungrowsg110cx
        return Sungrowsg110cx
    elif driver_name == "Solis":
        from backend.drivers.inverters.solis_S6_EH3P99_9K10_NV_YD_H import SolisS6HybridDriver
        return SolisS6HybridDriver
    raise ValueError(f"Unknown driver: {driver_name}")

def _get_transport(comm: dict):
    if comm["comm_type"] == "TCP":
        from backend.communication.modbus_tcp import ModbusTCP
        host = comm["host"]
        port = int(comm.get("port", 502))
        timeout = float(comm.get("timeout", 2.5))
        
        t = ModbusTCP(host=host, port=port, timeout=timeout)
        connected = False
        for attempt in range(2):
            if t.connect():
                connected = True
                break
            time.sleep(0.5)
            
        if not connected:
            raise ConnectionError(f"Không thể kết nối đến Modbus TCP {host}:{port} sau 2 lần thử. Vui lòng kiểm tra địa chỉ IP/Port hoặc thiết bị bận.")
        return t
    else:
        from backend.communication.modbus_rtu import ModbusRTU
        t = ModbusRTU(
            port=comm["com_port"].strip(),
            baudrate=comm.get("baudrate", 9600),
            bytesize=comm.get("databits", 8),
            parity=comm.get("parity", "N"),
            stopbits=comm.get("stopbits", 1),
            timeout=comm.get("timeout", 1.0),
        )
        if not t.connect():
            raise ConnectionError(f"Không thể mở cổng COM RS485 {comm.get('com_port')}.")
        return t

def background_scan(comm: dict):
    global scan_state
    
    driver_name = comm.get("driver", "Huawei")
    brand_selected = comm.get("brand")
    model_selected = comm.get("model")
    slave_start = int(comm.get("slave_id_start", 1))
    slave_end = int(comm.get("slave_id_end", 30))
    comm_id = _find_comm_id(comm)
    
    if comm_id:
        try:
            from backend.db_manager import MetadataDB
            db = MetadataDB(app_config.METADATA_DB)
            db.set_setting(f"scanning_comm_{comm_id}", "true")
        except Exception as e:
            logger.error(f"[Scan] Failed to set scanning status for comm {comm_id}: {e}")
    
    # Retrieve detect info if specified
    detect_info = None
    if brand_selected and model_selected:
        try:
            from backend.services.detect_service import SUNGROW_MODEL, HUAWEI_MODEL, SOLIS_MODEL
            if brand_selected.lower() == "sungrow":
                detect_info = next((m for m in SUNGROW_MODEL if m["model"] == model_selected), None)
            elif brand_selected.lower() == "huawei":
                detect_info = next((m for m in HUAWEI_MODEL if m["model"] == model_selected), None)
            elif brand_selected.lower() == "solis":
                detect_info = next((m for m in SOLIS_MODEL if m["model"] == model_selected), None)
        except Exception as e:
            logger.error(f"Error loading models from detect_service: {e}")


    with scan_state.lock:
        scan_state.is_running = True
        scan_state.stop_requested = False
        scan_state.progress = slave_start
        scan_state.total = slave_end
        scan_state.results = []
        scan_state.error = None

    transport = None
    try:
        DriverClass = _get_driver_class(driver_name, brand_selected, model_selected)
        transport = _get_transport(comm)
        
        for slave_id in range(slave_start, slave_end + 1):
            with scan_state.lock:
                if scan_state.stop_requested:
                    logger.info("[Scan] Cancellation requested by user.")
                    break
                scan_state.progress = slave_id

            success = False
            for attempt in range(1):
                try:
                    driver = DriverClass(transport, slave_id=slave_id)
                    info = driver.read_info()
                    # Check serial_number AND is_active (Huawei driver returns is_active=False on error)
                    if info and info.get("serial_number") and info.get("is_active", True):
                        
                        # If detect info exists, match type_code before appending
                        if detect_info:
                            hw_tcs = normalize_type_code(info.get("type_code"))
                            ex_tcs = normalize_type_code(detect_info.get("type_code"))
                            
                            if hw_tcs and ex_tcs and not (hw_tcs & ex_tcs):
                                logger.warning(f"[Scan] Slave {slave_id} rejected: Hardware TypeCode {info.get('type_code')} != Expected {detect_info.get('type_code')}")
                                continue  # Reject and move to next iteration
                            
                            try:
                                str_mppt = str(detect_info.get("string_mppt", "1"))
                                mppt_count = detect_info.get("mppt", 1)
                                if ";" in str_mppt:
                                    total_strings = sum(int(x) for x in str_mppt.split(";") if x.isdigit())
                                    info["strings_per_mppt"] = None  # Phức tạp nên không gán chung
                                  
                                else:
                                    spm = int(str_mppt)
                                    total_strings = spm * mppt_count
                                    info["strings_per_mppt"] = spm
                            except Exception:
                                mppt_count = detect_info.get("mppt", 1)
                                total_strings = 1
                                info["strings_per_mppt"] = 1
                            
                            info["mppt_count"] = mppt_count
                            info["string_count"] = total_strings
                            info["capacity_kw"] = detect_info.get("p_ac")
                            info["rate_ac_kw"] = detect_info.get("p_ac")
                            info["rate_dc_kwp"] = detect_info.get("p_dc")
                            # override brand and model if user manually selected them
                            info["brand"] = brand_selected
                            info["model"] = model_selected
                            
                            logger.info(f"[Scan] TypeCode valid: {info.get('type_code')} in {detect_info.get('type_code')}")

                        info["slave_id"] = slave_id
                        with scan_state.lock:
                            scan_state.results.append(info)
                        logger.info(f"[Scan] Found inverter at slave {slave_id}: {info.get('serial_number')}")
                        success = True
                        break
                except Exception as e:
                    logger.debug(f"[Scan] No inverter at slave {slave_id} (Attempt {attempt+1}): {e}")
                
                if not success and attempt == 0:
                    time.sleep(0.3)

    except Exception as e:
        logger.error(f"[Scan] Critical error: {e}", exc_info=True)
        with scan_state.lock:
            scan_state.error = str(e)
    finally:
        if transport:
            try: transport.close()
            except: pass
        with scan_state.lock:
            scan_state.is_running = False
            logger.info(f"[Scan] Finished. Found {len(scan_state.results)} inverters.")
        if comm_id:
            try:
                from backend.db_manager import MetadataDB
                db = MetadataDB(app_config.METADATA_DB)
                db.set_setting(f"scanning_comm_{comm_id}", "false")
            except Exception as e:
                logger.error(f"[Scan] Failed to clear scanning status for comm {comm_id}: {e}")

@router.post("/start")
def start_scan(background_tasks: BackgroundTasks, body: dict = Body(default=None)):
    global scan_state
    
    with scan_state.lock:
        if scan_state.is_running:
            return JSONResponse(status_code=400, content={"ok": False, "error": "A scan is already in progress."})
    
    from backend.api.comm_api import get_comm_service
    svc = get_comm_service()
    comms = svc.get_comm_config()
    comm = asdict(comms[-1]) if comms else {
        "comm_type": "TCP", "host": "127.0.0.1", "port": 502, "driver": "Huawei",
        "slave_id_start": 1, "slave_id_end": 30
    }
    
    if body and "comm" in body:
        comm.update(body["comm"])

    background_tasks.add_task(background_scan, comm)
    return {"ok": True, "message": "Scan started in background."}

@router.get("/status")
def get_scan_status():
    global scan_state
    with scan_state.lock:
        return {
            "is_running": scan_state.is_running,
            "progress": scan_state.progress,
            "total": scan_state.total,
            "found_count": len(scan_state.results),
            "inverters": scan_state.results,
            "error": scan_state.error,
            "stop_requested": scan_state.stop_requested
        }

@router.post("/stop")
def stop_scan():
    global scan_state
    with scan_state.lock:
        if scan_state.is_running:
            scan_state.stop_requested = True
            return {"ok": True, "message": "Stop requested."}
        return {"ok": False, "message": "No scan running."}

@router.post("/save")
def save_inverters(body: dict = Body(...)):
    try:
        svc = get_project_service()
        inverters_in = body.get("inverters", [])
        saved = 0
        for inv in inverters_in:
            project_id = inv.get("project_id")
            if not project_id: continue
            
            # Gán inverter_index tự động nếu chưa có
            if not inv.get("inverter_index"):
                existing = svc.metadata_db.get_inverters_by_project(project_id)
                next_idx = max((x.inverter_index for x in existing if x.inverter_index is not None), default=0) + 1
                inv["inverter_index"] = next_idx
                logger.info(f"[Scan] Auto-assigned inverter_index={next_idx} for inverter SN={inv.get('serial_number')}")

            # Loại bỏ các trường thừa sinh ra trong lúc scan không có trong DB Schema
            inv.pop("type_code", None)

            svc.metadata_db.upsert_inverter(InverterCreate(**inv))
            saved += 1
        return {"ok": True, "saved": saved}
    except Exception as e:
        logger.error(f"[save-inverters] Error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

def get_setup_service() -> SetupService:
    from backend.services.auth_service import AuthService
    svc = get_project_service()
    auth = AuthService(svc.metadata_db)
    return SetupService(auth, svc)

@router.post("/sync")
def sync_to_server(setup_svc: SetupService = Depends(get_setup_service)):
    try:
        svc = get_project_service()
        all_projects = svc.get_projects()
        total_inverters = 0
        for project in all_projects:
            # Sử dụng các hàm tương thích mới thêm vào SetupService
            setup_svc.sync_project_to_server(project.id)
            total_inverters += setup_svc.sync_inverters_to_server(project.id)
        return {"ok": True, "synced_projects": len(all_projects), "synced_inverters": total_inverters}
    except Exception as e:
        logger.error(f"[Sync] Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.get("/setup/status")
def get_setup_status():
    try:
        from dataclasses import asdict
        svc = get_project_service()
        all_projects = svc.get_projects()
        all_inverters = []
        for p in all_projects:
            invs = svc.metadata_db.get_inverters_by_project(p.id)
            for inv in invs:
                d = asdict(inv)
                d["project_id"] = p.id
                all_inverters.append(d)
        return {"projects": [asdict(p) for p in all_projects], "inverters": all_inverters}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.post("/batteries")
def scan_batteries_api(
    body: dict = Body(..., example={
        "project_id": 1,
        "driver": "PylontechBMS",
        "comm_type": "TCP",
        "host": "192.168.1.100",
        "port": 502,
        "slave_id_start": 1,
        "slave_id_end": 10
    }),
    setup_svc: SetupService = Depends(get_setup_service)
):
    """Quét Pin trực tiếp từ BMS qua RS485/TCP"""
    try:
        project_id = body.get("project_id")
        if not project_id:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Missing project_id"})
            
        driver_name = body.get("driver", "PylontechBMS")
        slave_start = int(body.get("slave_id_start", 1))
        slave_end = int(body.get("slave_id_end", 10))

        if "pylontech" in driver_name.lower():
            from backend.drivers.batteries.pylontech_bms import PylontechBMSDriver as DriverClass
        else:
            from backend.drivers.batteries.pylontech_bms import PylontechBMSDriver as DriverClass

        comm_type = body.get("comm_type", "TCP").upper()
        if comm_type == "TCP":
            host = body.get("host", "127.0.0.1")
            port = int(body.get("port", 502))
            try:
                from pymodbus.client import ModbusTcpClient
                transport = ModbusTcpClient(host=host, port=port, timeout=1)
                transport.connect()
            except Exception as conn_err:
                logger.error(f"[scan_batteries] TCP connect error: {conn_err}")
                return JSONResponse(status_code=500, content={"ok": False, "error": str(conn_err)})
        else:
            com_port = body.get("com_port", "/dev/ttyUSB0")
            baudrate = int(body.get("baudrate", 9600))
            try:
                from pymodbus.client import ModbusSerialClient
                transport = ModbusSerialClient(port=com_port, baudrate=baudrate, timeout=1)
                transport.connect()
            except Exception as conn_err:
                logger.error(f"[scan_batteries] Serial connect error: {conn_err}")
                return JSONResponse(status_code=500, content={"ok": False, "error": str(conn_err)})

        found_ids = setup_svc.scan_batteries(
            transport=transport,
            project_id=project_id,
            driver_class=DriverClass,
            slave_start=slave_start,
            slave_end=slave_end
        )
        try: transport.close()
        except: pass

        return {"ok": True, "found_count": len(found_ids), "battery_ids": found_ids}
    except Exception as e:
        logger.error(f"[scan_batteries] Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
