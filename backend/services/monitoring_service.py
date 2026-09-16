from typing import Optional, List, Dict, Any
from dataclasses import asdict

def find_raw_fault(brand: str, unified_code: int, old_instruction: str) -> Optional[int]:
    from backend.services.fault_mappings import FAULT_MAPS
    fault_map = FAULT_MAPS.get(brand.upper(), {})
    possible_faults = []
    for raw_code, info in fault_map.items():
        if info.get("id_unified") == unified_code:
            possible_faults.append((raw_code, info))
            
    if not possible_faults:
        return None
        
    if old_instruction:
        for raw_code, info in possible_faults:
            if info.get("repair_instruction") == old_instruction:
                return raw_code
                
    return possible_faults[0][0]

class MonitoringService:
    def __init__(self, metadata_db, realtime_db, cache_db=None):
        self.metadata_db = metadata_db
        self.realtime_db = realtime_db
        self.cache_db = cache_db

    def get_latest_project_data(self, project_id: int) -> Optional[dict]:
        data = self.realtime_db.get_latest_project_realtime(project_id)
        if not data:
            return None
        return asdict(data)

    def get_latest_inverter_data(self, inverter_id: int) -> Optional[dict]:
        if not self.cache_db:
            return None
        return self.cache_db.get_latest_realtime(inverter_id)

    def get_inverter_detail(self, inverter_id: int) -> dict:
        ac = self.realtime_db.get_latest_inverter_ac_realtime(inverter_id)
        mppts = self.realtime_db.get_latest_mppt_batch(inverter_id)
        strings = self.realtime_db.get_latest_string_batch(inverter_id)
        errors = self.realtime_db.get_inverter_errors(inverter_id)
        
        # Nâng cấp động các lỗi cũ từ database chưa có tiền tố
        try:
            inv = self.metadata_db.get_inverter_by_id(inverter_id)
            if inv and errors:
                brand = inv.brand.upper()
                from backend.services.fault_service import FaultService
                for e in errors:
                    if e.repair_instruction and not e.repair_instruction.startswith("mã lỗi ") and e.fault_code != 23:
                        raw_code = find_raw_fault(brand, e.fault_code, e.repair_instruction)
                        if raw_code is not None:
                            e.repair_instruction = FaultService.format_repair_instruction(brand, raw_code, e.repair_instruction)
        except Exception as ex:
            import logging
            logging.getLogger(__name__).warning(f"Failed to auto-format history error: {ex}")
            
        return {
            "ac": asdict(ac) if ac else None,
            "mppts": [asdict(m) for m in mppts],
            "strings": [asdict(s) for s in strings],
            "errors": [asdict(e) for e in errors[:10]]
        }

    def get_dashboard_summary(self) -> dict:
        projects = self.metadata_db.get_projects()
        inverters = self.metadata_db.get_all_inverters()
        
        inv_counts = {}
        for inv in inverters:
            inv_counts[inv.project_id] = inv_counts.get(inv.project_id, 0) + 1
            
        total_p_ac = 0.0
        total_e_daily = 0.0
        total_revenue = 0.0
        active_projects_count = 0
        project_summaries = []
        
        for p in projects:
            latest = self.realtime_db.get_latest_project_realtime(p.id)
            p_ac = latest.P_ac if (latest and latest.P_ac and latest.P_ac > 0) else 0.0
            e_daily = latest.E_daily if latest else 0.0

            # Fallback lấy tổng công suất từ từng inverter nếu project_realtime = 0
            if p_ac <= 0:
                invs = self.metadata_db.get_inverters_by_project(p.id)
                sum_ac = 0.0
                for inv in invs:
                    ac = self.realtime_db.get_latest_inverter_ac_realtime(inv.id)
                    if ac and ac.P_ac and ac.P_ac > 0:
                        sum_ac += ac.P_ac
                if sum_ac > 0:
                    p_ac = sum_ac
            
            revenue = e_daily * (p.elec_price_per_kwh or 0.0)
            
            total_p_ac += p_ac
            total_e_daily += e_daily
            total_revenue += revenue
            
            if p_ac > 0: active_projects_count += 1
            
            project_summaries.append({
                "id": p.id,
                "name": p.name,
                "inverter_count": inv_counts.get(p.id, 0),
                "capacity_kwp": p.capacity_kwp,
                "ac_capacity_kw": p.ac_capacity_kw,
                "elec_meter_no": p.elec_meter_no,
                "p_ac": p_ac,
                "e_daily": e_daily,
                "revenue": revenue,
                "status": "online" if p_ac > 0 else "offline"
            })

        power_flow_data = self.get_power_flow()
                
        return {
            "total_p_ac": total_p_ac,
            "total_e_daily": total_e_daily,
            "total_revenue": total_revenue,
            "active_projects_count": active_projects_count,
            "total_projects": len(projects),
            "total_inverters": len(inverters),
            "projects": project_summaries,
            "power_flow": power_flow_data
        }

    def get_power_flow(self, project_id: Optional[int] = None) -> dict:
        """
        Tính toán dữ liệu sơ đồ dòng công suất Power Flow chuẩn Hãng cho 6 nhánh thiết bị:
        - pv_kw: Công suất PV (DC Power kW) & sản lượng ngày (kWh)
        - inverter_kw: Công suất hòa lưới (AC Power kW) & số lượng inverter (x2)
        - grid_kw: Công suất lưới (Grid Import/Export kW) & nhập/xuất ngày (kWh)
        - grid_load_kw: Công suất phụ tải bám lưới (Grid Load kW) & tiêu thụ ngày (kWh)
        - battery_kw: Công suất sạc/xả pin (kW), phần trăm SOC%, sạc/xả ngày & số pack pin (x2)
        - backup_load_kw: Công suất phụ tải độc lập (Backup Load kW) & tiêu thụ ngày (kWh)
        - updated_at: Thời điểm cập nhật
        """
        from datetime import datetime
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S (UTC+07:00)")

        # Lấy thông tin số lượng thiết bị từ MetadataDB
        proj_list = self.metadata_db.get_projects()
        target_proj_id = project_id if project_id else (proj_list[0].id if proj_list else 1)
        
        inverters = self.metadata_db.get_inverters_by_project(target_proj_id)
        inv_count = len(inverters) if inverters else 1
        
        try:
            batteries = self.metadata_db.get_batteries_by_project(target_proj_id)
            batt_count = len(batteries) if batteries else 1
        except Exception:
            batt_count = 1

        p_dc_w = 0.0
        p_ac_w = 0.0
        e_daily_pv = 0.0
        soc_val = 100
        last_updated = now_str

        # 1. Lấy dữ liệu từ AC cache (RAM)
        ac_rows = self.cache_db.get_ac_cache_by_project(target_proj_id) if self.cache_db else []
        
        if ac_rows:
            for r in ac_rows:
                p_dc_w += (r.get("p_dc_w") or r.get("P_dc") or 0.0)
                p_ac_w += (r.get("P_ac") or r.get("p_inv_w") or 0.0)
                e_daily_pv += (r.get("E_daily") or r.get("e_daily") or 0.0)
                if r.get("bms_batt_soc") is not None:
                    soc_val = int(r.get("bms_batt_soc"))
                if r.get("updated_at"):
                    try:
                        ts = datetime.fromisoformat(r["updated_at"].replace(" ", "T"))
                        last_updated = ts.strftime("%d/%m/%Y %H:%M:%S (UTC+07:00)")
                    except Exception:
                        last_updated = str(r.get("updated_at"))

        # Fallback lấy dữ liệu từ RealtimeDB nếu p_ac_w = 0 hoặc RAM Cache rỗng
        if p_ac_w <= 0 and p_dc_w <= 0:
            p_real = self.realtime_db.get_latest_project_realtime(target_proj_id)
            if p_real:
                p_ac_w = (p_real.P_ac or 0.0) * 1000.0 if (p_real.P_ac or 0.0) < 200 else (p_real.P_ac or 0.0)
                p_dc_w = (p_real.P_dc or 0.0) * 1000.0 if (p_real.P_dc or 0.0) < 200 else (p_real.P_dc or 0.0)
                if not e_daily_pv or e_daily_pv <= 0:
                    e_daily_pv = p_real.E_daily or 0.0
                if p_real.created_at and last_updated == now_str:
                    try:
                        ts = datetime.fromisoformat(p_real.created_at.replace(" ", "T"))
                        last_updated = ts.strftime("%d/%m/%Y %H:%M:%S (UTC+07:00)")
                    except Exception:
                        last_updated = str(p_real.created_at)

            # Nếu vẫn = 0, cộng dồn trực tiếp từ inverter_ac_realtime
            if p_ac_w <= 0:
                invs = self.metadata_db.get_inverters_by_project(target_proj_id)
                sum_ac_w = 0.0
                for inv in invs:
                    ac = self.realtime_db.get_latest_inverter_ac_realtime(inv.id)
                    if ac and ac.P_ac and ac.P_ac > 0:
                        sum_ac_w += (ac.P_ac * 1000.0 if ac.P_ac < 200 else ac.P_ac)
                        if not e_daily_pv or e_daily_pv <= 0:
                            e_daily_pv += (ac.E_daily or 0.0)
                if sum_ac_w > 0:
                    p_ac_w = sum_ac_w
                    if p_dc_w <= 0:
                        p_dc_w = sum_ac_w

        # 2. Lấy dữ liệu từ Battery cache (hoặc fallback RealtimeDB)
        batt_p_w = 0.0
        e_batt_charge_daily = 0.0
        e_batt_discharge_daily = 0.0
        if self.cache_db:
            try:
                with self.cache_db._connect() as conn:
                    query = "SELECT bms_batt_p, inv_batt_p, bms_batt_soc, e_charge_daily, e_discharge_daily, updated_at FROM battery_cache WHERE project_id = ?"
                    batt_row = conn.execute(query, (target_proj_id,)).fetchone()
                    if batt_row:
                        batt_dict = dict(batt_row)
                        batt_p_w = batt_dict.get("bms_batt_p") if batt_dict.get("bms_batt_p") is not None else (batt_dict.get("inv_batt_p") or 0.0)
                        e_batt_charge_daily = batt_dict.get("e_charge_daily") or 0.0
                        e_batt_discharge_daily = batt_dict.get("e_discharge_daily") or 0.0
                        if batt_dict.get("bms_batt_soc") is not None:
                            soc_val = int(batt_dict.get("bms_batt_soc"))
            except Exception:
                batt_p_w = 0.0

        if batt_p_w == 0.0 and self.realtime_db:
            try:
                batt_rt_list = self.realtime_db.get_latest_battery_batch(target_proj_id)
                if batt_rt_list:
                    b_rt = batt_rt_list[0]
                    batt_p_w = b_rt.bms_batt_p if b_rt.bms_batt_p != 0 else b_rt.inv_batt_p
                    e_batt_charge_daily = b_rt.e_charge_daily
                    e_batt_discharge_daily = b_rt.e_discharge_daily
                    if b_rt.bms_batt_soc > 0:
                        soc_val = int(b_rt.bms_batt_soc)
            except Exception:
                pass

        # 3. Lấy dữ liệu từ Load cache (hoặc fallback RealtimeDB)
        p_load_w = 0.0
        s_backup_w = 0.0
        e_grid_load_daily = 0.0
        e_backup_load_daily = 0.0
        if self.cache_db:
            try:
                with self.cache_db._connect() as conn:
                    query = "SELECT p_load, s_backup_load, e_daily, e_backup_daily, updated_at FROM load_cache WHERE project_id = ?"
                    load_row = conn.execute(query, (target_proj_id,)).fetchone()
                    if load_row:
                        load_dict = dict(load_row)
                        p_load_w = load_dict.get("p_load") or 0.0
                        s_backup_w = load_dict.get("s_backup_load") or 0.0
                        e_grid_load_daily = load_dict.get("e_daily") or 0.0
                        e_backup_load_daily = load_dict.get("e_backup_daily") or 0.0
            except Exception:
                pass

        if p_load_w == 0.0 and self.realtime_db:
            try:
                load_rt_list = self.realtime_db.get_latest_load_batch(target_proj_id)
                if load_rt_list:
                    l_rt = load_rt_list[0]
                    p_load_w = l_rt.p_load
                    s_backup_w = l_rt.s_backup_load
                    e_grid_load_daily = l_rt.e_daily
                    e_backup_load_daily = l_rt.e_backup_daily
            except Exception:
                pass

        # 4. Lấy dữ liệu từ Meter cache (hoặc fallback RealtimeDB)
        p_grid_w = 0.0
        e_grid_import_daily = 0.0
        e_grid_export_daily = 0.0
        if self.cache_db:
            try:
                with self.cache_db._connect() as conn:
                    query = "SELECT P_total, imp_pt_today, exp_pt_today, updated_at FROM meter_cache WHERE project_id = ?"
                    meter_row = conn.execute(query, (target_proj_id,)).fetchone()
                    if meter_row:
                        meter_dict = dict(meter_row)
                        p_grid_w = meter_dict.get("P_total") or 0.0
                        e_grid_import_daily = meter_dict.get("imp_pt_today") or 0.0
                        e_grid_export_daily = meter_dict.get("exp_pt_today") or 0.0
            except Exception:
                pass

        if p_grid_w == 0.0 and self.realtime_db:
            try:
                meter_rt_list = self.realtime_db.get_latest_meter_batch(target_proj_id)
                if meter_rt_list:
                    m_rt = meter_rt_list[0]
                    p_grid_w = m_rt.P_total
                    e_grid_import_daily = m_rt.imp_pt_today
                    e_grid_export_daily = m_rt.exp_pt_today
            except Exception:
                pass

        # Nếu không có DC riêng nhưng có AC -> PV power = max(p_dc_w, p_ac_w)
        if p_dc_w <= 0 and p_ac_w > 0:
            p_dc_w = p_ac_w

        # Tự động tính Tải lưới nếu công suất Tải lưới chưa có sẵn: Load = AC_inv + Grid_import - Battery_charge
        if p_load_w <= 0 and p_ac_w > 0:
            p_load_w = p_ac_w + (abs(p_grid_w) if p_grid_w < 0 else 0) - (abs(batt_p_w) if batt_p_w < 0 else 0)

        # Đổi đơn vị W -> kW
        pv_dc_kw = round(p_dc_w / 1000.0 if p_dc_w > 200 else p_dc_w, 3)
        inv_kw = round(p_ac_w / 1000.0 if p_ac_w > 200 else p_ac_w, 3)
        grid_kw = round(p_grid_w / 1000.0 if abs(p_grid_w) > 200 else p_grid_w, 3)
        grid_load_kw = round(p_load_w / 1000.0 if p_load_w > 200 else p_load_w, 3)
        batt_kw = round(batt_p_w / 1000.0 if abs(batt_p_w) > 200 else batt_p_w, 3)
        backup_load_kw = round(s_backup_w / 1000.0 if s_backup_w > 200 else s_backup_w, 3)

        # Xác định chiều sạc/xả pin (0: Charging, 1: Discharging, -1: Idle)
        batt_dir = -1
        if abs(batt_kw) > 0.01:
            if batt_p_w < 0:
                batt_dir = 0  # Charging (Sạc)
            else:
                batt_dir = 1  # Discharging (Xả)

        return {
            "pv_kw": max(0.0, inv_kw),
            "pv_dc_kw": max(0.0, pv_dc_kw),
            "pv_daily_kwh": round(e_daily_pv, 1),
            "inverter_kw": max(0.0, inv_kw),
            "inverter_count": inv_count,
            "grid_kw": abs(grid_kw),
            "grid_direction": "export" if grid_kw > 0.01 else ("import" if grid_kw < -0.01 else "none"),
            "grid_import_daily_kwh": round(e_grid_import_daily, 1),
            "grid_export_daily_kwh": round(e_grid_export_daily, 1),
            "grid_load_kw": max(0.0, grid_load_kw),
            "grid_load_daily_kwh": round(e_grid_load_daily, 1),
            "battery_kw": abs(batt_kw),
            "battery_direction": batt_dir,
            "battery_soc": soc_val,
            "battery_count": batt_count,
            "battery_charge_daily_kwh": round(e_batt_charge_daily, 1),
            "battery_discharge_daily_kwh": round(e_batt_discharge_daily, 1),
            "backup_load_kw": max(0.0, backup_load_kw),
            "backup_load_daily_kwh": round(e_backup_load_daily, 1),
            "updated_at": last_updated
        }

    def get_project_history(self, project_id: int, start: str, end: str) -> List[dict]:
        data = self.realtime_db.get_project_realtime_range(project_id, start, end)
        return [asdict(d) for d in data]

    def get_inverter_history(self, inverter_id: int, start: str, end: str) -> List[dict]:
        data = self.realtime_db.get_inverter_ac_range(inverter_id, start, end)
        return [asdict(d) for d in data]
