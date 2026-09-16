"""
Driver Modbus RTU / TCP cho Inverter Solis Hybrid 99.9kW
Model: S6-EH3P99.9K10-NV-YD-H
Dựa trên tài liệu chính thức: RS485_MODBUS Hybrid Inverter.docx
Hỗ trợ đầy đủ đọc thông số Inverter (10 MPPT / 20 Strings), Lưới (Grid/Meter 33251~33286), Phụ tải (Load/Backup/Smart) và Pin lưu trữ (Battery/BMS).
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from backend.drivers.inverters.base import BaseDriver
except ImportError:
    class BaseDriver:
        pass

logger = logging.getLogger(__name__)


class SolisS6HybridDriver(BaseDriver):
    """
    Driver cho Inverter Solis Hybrid S6-EH3P99.9K10-NV-YD-H (99.9kW).
    Đọc dữ liệu Modbus RTU/TCP qua transport (Pymodbus client).
    """

    def __init__(self, transport=None, slave_id: int = 1):
        self.transport = transport
        self.slave_id = slave_id

    # =========================================================
    # REGISTER MAP (BẢN ĐỒ THANH GHI CHÍNH XÁC 100% TỪ DOCX)
    # =========================================================

    def register_map(self) -> Dict[str, Any]:
        """
        Bản đồ chi tiết 100% các thanh ghi Modbus (Input & Holding)
        Được trích xuất trực tiếp từ tài liệu: RS485_MODBUS Hybrid Inverter.docx
        """
        return {
            "info": [
                {"name": "dsp_version", "address": 33001, "length": 1, "type": "uint16", "scale": None, "desc": "DSP Software Major Version"},
                {"name": "hmi_version", "address": 33002, "length": 1, "type": "uint16", "scale": None, "desc": "HMI Software Major Version"},
                {"name": "serial_number", "address": 33004, "length": 16, "type": "ascii", "scale": None, "desc": "Inverter Serial Number (SN_1 ~ SN_16)"},
            ],
            "ac": [
                {"name": "v_a", "address": 33073, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "A Phase AC Voltage"},
                {"name": "v_b", "address": 33074, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "B Phase AC Voltage"},
                {"name": "v_c", "address": 33075, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "C Phase AC Voltage"},
                {"name": "i_a", "address": 33076, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "A Phase AC Current"},
                {"name": "i_b", "address": 33077, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "B Phase AC Current"},
                {"name": "i_c", "address": 33078, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "C Phase AC Current"},
                {"name": "p_ac", "address": 33079, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "AC Active Power Value"},
                {"name": "q_ac", "address": 33081, "length": 2, "type": "sint32", "scale": 1, "unit": "VAr", "desc": "AC Reactive Power Value"},
                {"name": "s_ac", "address": 33083, "length": 2, "type": "sint32", "scale": 1, "unit": "VA", "desc": "AC Apparent Power Value"},
                {"name": "temp_c", "address": 33093, "length": 1, "type": "sint16", "scale": 0.1, "unit": "C", "desc": "Inverter Module Temperature (AC NTC/IGBT)"},
                {"name": "grid_hz", "address": 33094, "length": 1, "type": "uint16", "scale": 0.01, "unit": "Hz", "desc": "Grid Frequency"},
                {"name": "e_total", "address": 33029, "length": 2, "type": "uint32", "scale": 1, "unit": "kWh", "desc": "Total PV Energy Generation"},
                {"name": "e_daily", "address": 33035, "length": 1, "type": "uint16", "scale": 0.1, "unit": "kWh", "desc": "Today's PV Energy Generation"},
            ],
            "dc": [
                {"name": "p_dc_input", "address": 33057, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Total PV Input Power"},
                {"name": "p_dc_total", "address": 34903, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Hybrid Inverters PV Total Power"},
                # MPPT 1..4 (33049..33056)
                {"name": "mppt_1_voltage", "address": 33049, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 1"},
                {"name": "mppt_1_current", "address": 33050, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 1"},
                {"name": "mppt_2_voltage", "address": 33051, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 2"},
                {"name": "mppt_2_current", "address": 33052, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 2"},
                {"name": "mppt_3_voltage", "address": 33053, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 3"},
                {"name": "mppt_3_current", "address": 33054, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 3"},
                {"name": "mppt_4_voltage", "address": 33055, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 4"},
                {"name": "mppt_4_current", "address": 33056, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 4"},
                # MPPT 5..8 (33059..33066)
                {"name": "mppt_5_voltage", "address": 33059, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 5"},
                {"name": "mppt_5_current", "address": 33060, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 5"},
                {"name": "mppt_6_voltage", "address": 33061, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 6"},
                {"name": "mppt_6_current", "address": 33062, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 6"},
                {"name": "mppt_7_voltage", "address": 33063, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 7"},
                {"name": "mppt_7_current", "address": 33064, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 7"},
                {"name": "mppt_8_voltage", "address": 33065, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 8"},
                {"name": "mppt_8_current", "address": 33066, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 8"},
                # MPPT 9..10 (34498..34501)
                {"name": "mppt_9_voltage", "address": 34498, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 9"},
                {"name": "mppt_9_current", "address": 34499, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 9"},
                {"name": "mppt_10_voltage", "address": 34500, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "PV DC Voltage 10"},
                {"name": "mppt_10_current", "address": 34501, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "PV DC Current 10"},
            ],
            "grid": [
                {"name": "u_a", "address": 33251, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Meter AC Voltage Phase A"},
                {"name": "i_a", "address": 33252, "length": 1, "type": "uint16", "scale": 0.01, "unit": "A", "desc": "Meter AC Current Phase A"},
                {"name": "u_b", "address": 33253, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Meter AC Voltage Phase B"},
                {"name": "i_b", "address": 33254, "length": 1, "type": "uint16", "scale": 0.01, "unit": "A", "desc": "Meter AC Current Phase B"},
                {"name": "u_c", "address": 33255, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Meter AC Voltage Phase C"},
                {"name": "i_c", "address": 33256, "length": 1, "type": "uint16", "scale": 0.01, "unit": "A", "desc": "Meter AC Current Phase C"},
                {"name": "p_a", "address": 33257, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Meter Active Power Phase A"},
                {"name": "p_b", "address": 33259, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Meter Active Power Phase B"},
                {"name": "p_c", "address": 33261, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Meter Active Power Phase C"},
                {"name": "p_grid_total", "address": 33263, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Meter Total Active Power"},
                {"name": "q_grid_total", "address": 33271, "length": 2, "type": "sint32", "scale": 1, "unit": "VAr", "desc": "Meter Total Reactive Power"},
                {"name": "s_grid_total", "address": 33279, "length": 2, "type": "sint32", "scale": 1, "unit": "VA", "desc": "Meter Total Apparent Power"},
                {"name": "pf", "address": 33281, "length": 1, "type": "sint16", "scale": 0.01, "unit": "", "desc": "Meter Power Factor"},
                {"name": "f", "address": 33282, "length": 1, "type": "uint16", "scale": 0.01, "unit": "Hz", "desc": "Meter Grid Frequency"},
                {"name": "e_import_total", "address": 33283, "length": 2, "type": "uint32", "scale": 0.01, "unit": "kWh", "desc": "Meter Total Active Energy Imported"},
                {"name": "e_export_total", "address": 33285, "length": 2, "type": "uint32", "scale": 0.01, "unit": "kWh", "desc": "Meter Total Active Energy Exported"},
            ],
            "load": [
                {"name": "e_total", "address": 33177, "length": 2, "type": "uint32", "scale": 1, "unit": "kWh", "desc": "Load Total Power Consumption"},
                {"name": "e_daily", "address": 33179, "length": 1, "type": "uint16", "scale": 0.1, "unit": "kWh", "desc": "Load Daily Power Consumption"},
                {"name": "p_load_low", "address": 33147, "length": 1, "type": "uint16", "scale": 1, "unit": "W", "desc": "Grid-side Home Load Power (Low)"},
                {"name": "p_load_high", "address": 34343, "length": 1, "type": "uint16", "scale": 1, "unit": "W", "desc": "Grid-side Home Load Power (High)"},
                {"name": "u_backup_a", "address": 33137, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Backup Port AC Voltage Phase A"},
                {"name": "i_backup_a", "address": 33138, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "Backup Port AC Current Phase A"},
                {"name": "u_backup_b", "address": 33153, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Backup Port AC Voltage Phase B"},
                {"name": "i_backup_b", "address": 33154, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "Backup Port AC Current Phase B"},
                {"name": "u_backup_c", "address": 33155, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Backup Port AC Voltage Phase C"},
                {"name": "i_backup_c", "address": 33156, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "Backup Port AC Current Phase C"},
                {"name": "p_backup_a", "address": 33521, "length": 1, "type": "sint16", "scale": 10, "unit": "W", "desc": "Backup Port Phase A Active Power"},
                {"name": "p_backup_b", "address": 33524, "length": 1, "type": "sint16", "scale": 10, "unit": "W", "desc": "Backup Port Phase B Active Power"},
                {"name": "p_backup_c", "address": 33527, "length": 1, "type": "sint16", "scale": 10, "unit": "W", "desc": "Backup Port Phase C Active Power"},
                {"name": "s_backup_load", "address": 34613, "length": 2, "type": "sint32", "scale": 1, "unit": "VA", "desc": "Backup Load Total Apparent Power"},
                {"name": "e_backup_total", "address": 33590, "length": 2, "type": "uint32", "scale": 1, "unit": "kWh", "desc": "Backup Load Total Power Consumption"},
                {"name": "e_backup_daily", "address": 33596, "length": 1, "type": "uint16", "scale": 0.1, "unit": "kWh", "desc": "Backup Load Daily Power Consumption"},
                {"name": "u_smart_a", "address": 34328, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Smart Port Phase A AC Voltage"},
                {"name": "u_smart_b", "address": 34329, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Smart Port Phase B AC Voltage"},
                {"name": "u_smart_c", "address": 34330, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Smart Port Phase C AC Voltage"},
                {"name": "i_smart_a", "address": 34331, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "Smart Port Phase A AC Current"},
                {"name": "i_smart_b", "address": 34332, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "Smart Port Phase B AC Current"},
                {"name": "i_smart_c", "address": 34333, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "Smart Port Phase C AC Current"},
                {"name": "p_smart_a", "address": 34391, "length": 1, "type": "sint16", "scale": 10, "unit": "W", "desc": "Smart Port Phase A Active Power"},
                {"name": "p_smart_b", "address": 34392, "length": 1, "type": "sint16", "scale": 10, "unit": "W", "desc": "Smart Port Phase B Active Power"},
                {"name": "p_smart_c", "address": 34393, "length": 1, "type": "sint16", "scale": 10, "unit": "W", "desc": "Smart Port Phase C Active Power"},
                {"name": "s_smart_load", "address": 34619, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Smart Load Total Active Power"},
                {"name": "e_smart_total", "address": 34411, "length": 2, "type": "uint32", "scale": 1, "unit": "kWh", "desc": "Smart Load Total Power Consumption"},
                {"name": "e_smart_daily", "address": 34413, "length": 2, "type": "uint32", "scale": 1, "unit": "kWh", "desc": "Smart Load Daily Power Consumption"},
            ],
            "battery": [
                {"name": "inv_batt_u", "address": 33133, "length": 1, "type": "uint16", "scale": 0.1, "unit": "V", "desc": "Battery 1 Real-time Voltage"},
                {"name": "inv_batt_i", "address": 33134, "length": 1, "type": "sint16", "scale": 0.1, "unit": "A", "desc": "Battery 1 Real-time Current"},
                {"name": "batt_direction", "address": 33135, "length": 1, "type": "uint16", "scale": None, "unit": "", "desc": "Battery Charge/Discharge Status (0: Charging, 1: Discharging)"},
                {"name": "soc", "address": 33139, "length": 1, "type": "uint16", "scale": 1, "unit": "%", "desc": "Battery 1 State of Charge (SOC)"},
                {"name": "soh", "address": 33140, "length": 1, "type": "uint16", "scale": 1, "unit": "%", "desc": "Battery 1 State of Health (SOH)"},
                {"name": "inv_batt_p", "address": 33149, "length": 2, "type": "sint32", "scale": 1, "unit": "W", "desc": "Battery 1 Real-time Power"},
                {"name": "bms_max_charge_i", "address": 33041, "length": 1, "type": "uint16", "scale": 0.1, "unit": "A", "desc": "Maximum Charge/Discharge Current"},
                {"name": "lead_acid_temp", "address": 33096, "length": 1, "type": "sint16", "scale": 0.1, "unit": "C", "desc": "Lead-Acid Battery Ambient Temperature"},
                {"name": "e_charge_total", "address": 33161, "length": 2, "type": "uint32", "scale": 1, "unit": "kWh", "desc": "Battery Total Charging Energy"},
                {"name": "e_charge_daily", "address": 33163, "length": 1, "type": "uint16", "scale": 0.1, "unit": "kWh", "desc": "Battery Daily Charging Energy"},
                {"name": "e_discharge_total", "address": 33165, "length": 2, "type": "uint32", "scale": 1, "unit": "kWh", "desc": "Battery Total Discharging Energy"},
                {"name": "e_discharge_daily", "address": 33167, "length": 1, "type": "uint16", "scale": 0.1, "unit": "kWh", "desc": "Battery Daily Discharging Energy"},
                {"name": "bms_state", "address": 33295, "length": 1, "type": "uint16", "scale": None, "unit": "", "desc": "Battery 1 BMS Real-time Status"},
                {"name": "min_cell_volt", "address": 34348, "length": 1, "type": "uint16", "scale": 0.001, "unit": "V", "desc": "Battery 1 BMS Minimum Cell Voltage"},
                {"name": "max_cell_volt", "address": 34349, "length": 1, "type": "uint16", "scale": 0.001, "unit": "V", "desc": "Battery 1 BMS Maximum Cell Voltage"},
                {"name": "min_cell_temp", "address": 34350, "length": 1, "type": "uint16", "scale": 0.1, "unit": "C", "desc": "Battery 1 BMS Minimum Cell Temperature"},
                {"name": "max_cell_temp", "address": 34351, "length": 1, "type": "uint16", "scale": 0.1, "unit": "C", "desc": "Battery 1 BMS Maximum Cell Temperature"},
                {"name": "battery_model_code", "address": 43009, "length": 1, "type": "uint16", "scale": None, "unit": "", "desc": "Battery Manufacturer Model Code"},
                {"name": "discharge_volt_limit", "address": 43011, "length": 1, "type": "uint16", "scale": 1, "unit": "%", "desc": "Over-Discharge SOC Setting"},
            ],
            "errors": [
                {"name": "fault_code", "address": 33095, "length": 1, "type": "uint16", "scale": None, "desc": "Inverter Current Status / Main Fault Code"},
                {"name": "fault_sub_code", "address": 33070, "length": 1, "type": "uint16", "scale": None, "desc": "Warning / Fault Message Sub-Data"},
                {"name": "operating_status", "address": 33121, "length": 1, "type": "uint16", "scale": None, "desc": "Operating Status Bitfield (Appendix 4)"},
                {"name": "drm_status", "address": 33098, "length": 1, "type": "uint16", "scale": None, "desc": "Current DRM Status"},
            ]
        }

    # =========================================================
    # HELPER READ & CONVERT METHODS
    # =========================================================

    def _read_input_registers(self, start_address: int, count: int) -> Optional[List[int]]:
        if not self.transport:
            return None
        try:
            if hasattr(self.transport, "read_input_registers"):
                res = self.transport.read_input_registers(address=start_address, count=count, slave=self.slave_id)
            else:
                res = self.transport.read_input_registers(start_address, count, unit=self.slave_id)
            
            if hasattr(res, "isError") and res.isError():
                logger.warning(f"Modbus read input error at {start_address}, count {count}: {res}")
                return None
            return res.registers
        except Exception as e:
            logger.error(f"Failed to read input registers at {start_address}: {e}")
            return None

    def _read_holding_registers(self, start_address: int, count: int) -> Optional[List[int]]:
        if not self.transport:
            return None
        try:
            if hasattr(self.transport, "read_holding_registers"):
                res = self.transport.read_holding_registers(address=start_address, count=count, slave=self.slave_id)
            else:
                res = self.transport.read_holding_registers(start_address, count, unit=self.slave_id)

            if hasattr(res, "isError") and res.isError():
                logger.warning(f"Modbus read holding error at {start_address}, count {count}: {res}")
                return None
            return res.registers
        except Exception as e:
            logger.error(f"Failed to read holding registers at {start_address}: {e}")
            return None

    @staticmethod
    def _to_u16(regs: List[int], idx: int = 0) -> Optional[int]:
        if not regs or idx >= len(regs) or regs[idx] is None:
            return None
        return regs[idx] & 0xFFFF

    @staticmethod
    def _to_s16(regs: List[int], idx: int = 0) -> Optional[int]:
        if not regs or idx >= len(regs) or regs[idx] is None:
            return None
        val = regs[idx] & 0xFFFF
        if val & 0x8000:
            val -= 0x10000
        return val

    @staticmethod
    def _to_u32(regs: List[int], idx: int = 0) -> Optional[int]:
        if not regs or idx + 1 >= len(regs) or regs[idx] is None or regs[idx + 1] is None:
            return None
        w0 = regs[idx] & 0xFFFF
        w1 = regs[idx + 1] & 0xFFFF
        val1 = (w0 << 16) | w1
        val2 = (w1 << 16) | w0
        if val1 > 1000000000:
            return val2
        return val1

    @staticmethod
    def _to_s32(regs: List[int], idx: int = 0) -> Optional[int]:
        if not regs or idx + 1 >= len(regs) or regs[idx] is None or regs[idx + 1] is None:
            return None
        w0 = regs[idx] & 0xFFFF
        w1 = regs[idx + 1] & 0xFFFF
        val1 = (w0 << 16) | w1
        val2 = (w1 << 16) | w0
        if val1 & 0x80000000:
            val1 -= 0x100000000
        if val2 & 0x80000000:
            val2 -= 0x100000000
        if abs(val1) > 10000000:
            return val2
        return val1

    # =========================================================
    # 1. THÔNG TIN INVERTER (INFO)
    # =========================================================

    def read_info(self) -> Dict[str, Any]:
        """Đọc Serial Number và Firmware Version (33000 ~ 33021)."""
        raw = self._read_input_registers(33004, 16)
        sn = ""
        is_active = False
        if raw:
            chars = []
            for val in raw:
                if not val:
                    continue
                h = (val >> 8) & 0xFF
                l = val & 0xFF
                if 32 <= h <= 126:
                    chars.append(chr(h))
                if 32 <= l <= 126:
                    chars.append(chr(l))
            sn = "".join(chars).strip()

            if not sn:
                for val in raw:
                    if val:
                        sn += f"{val:04X}"
                sn = sn.strip("0")
            
            if sn:
                is_active = True

        dsp_raw = self._read_input_registers(33001, 1)
        dsp_ver = f"{self._to_u16(dsp_raw):X}" if dsp_raw else "1.0"

        return {
            "brand": "Solis",
            "model": "S6-EH3P99.9K10-NV-YD-H",
            "serial_number": sn if is_active else "",
            "is_active": is_active,
            "firmware_version": dsp_ver,
            "rate_ac_kw": 99.9,
            "rate_dc_kwp": 120.0,
            "phase_count": 3,
            "mppt_count": 10,
            "string_count": 20,
            "slave_id": self.slave_id
        }

    # =========================================================
    # 2. ĐO LƯỜNG AC INVERTER (AC DATA)
    # =========================================================

    def read_ac(self) -> Dict[str, Any]:
        """Đọc đầy đủ thông số AC: Điện áp, Dòng điện, P_ac (33079), Q_ac (33081), S_ac (33083), PF, Tần số, Nhiệt độ và Sản lượng."""
        raw_vi = self._read_input_registers(33073, 6)
        v_a = self._to_u16(raw_vi, 0) * 0.1 if raw_vi else None
        v_b = self._to_u16(raw_vi, 1) * 0.1 if raw_vi else None
        v_c = self._to_u16(raw_vi, 2) * 0.1 if raw_vi else None
        i_a = self._to_u16(raw_vi, 3) * 0.1 if raw_vi else None
        i_b = self._to_u16(raw_vi, 4) * 0.1 if raw_vi else None
        i_c = self._to_u16(raw_vi, 5) * 0.1 if raw_vi else None

        # Đọc khối công suất 33079 ~ 33084 (6 registers): P_ac (S32), Q_ac (S32), S_ac (S32)
        raw_pow = self._read_input_registers(33079, 6)
        p_ac = float(self._to_s32(raw_pow, 0)) if raw_pow else None
        q_ac = float(self._to_s32(raw_pow, 2)) if raw_pow else None
        s_ac = float(self._to_s32(raw_pow, 4)) if raw_pow else None

        # Nếu không đọc được P_ac từ 33079, thử fallback 33057 (PV input power)
        if p_ac is None:
            raw_p_dc_in = self._read_input_registers(33057, 2)
            p_ac = float(self._to_s32(raw_p_dc_in, 0)) if raw_p_dc_in else None

        # Tính toán Hệ số công suất Power Factor (PF) = P_ac / S_ac
        pf = None
        if p_ac is not None and s_ac is not None and s_ac > 0:
            pf = round(abs(p_ac) / s_ac, 3)
            if pf > 1.0:
                pf = 1.0

        raw_f = self._read_input_registers(33094, 1)
        freq = self._to_u16(raw_f, 0) * 0.01 if raw_f else None

        raw_temp = self._read_input_registers(33093, 1)
        temp_c = self._to_s16(raw_temp, 0) * 0.1 if raw_temp else None

        raw_e_tot = self._read_input_registers(33029, 2)
        e_total = float(self._to_u32(raw_e_tot, 0)) if raw_e_tot else None

        raw_e_day = self._read_input_registers(33035, 1)
        e_daily = self._to_u16(raw_e_day, 0) * 0.1 if raw_e_day else None

        return {
            "IR": None,
            "Temp_C": temp_c,
            "P_ac": p_ac,
            "Q_ac": q_ac,
            "V_a": v_a,
            "V_b": v_b,
            "V_c": v_c,
            "I_a": i_a,
            "I_b": i_b,
            "I_c": i_c,
            "PF": pf,
            "H": freq,
            "E_daily": e_daily,
            "E_total": e_total
        }

    # =========================================================
    # 3. ĐO LƯỜNG DC & 10 MPPTS & 20 STRINGS
    # =========================================================

    def read_dc(self) -> Dict[str, Any]:
        """
        Đọc chi tiết 10 MPPTs và 20 Strings chuẩn theo tài liệu Solis Hybrid.
        MPPT 1..4: 33049..33056
        Total PV Power: 33057..33058 (S32)
        MPPT 5..8: 33059..33066
        MPPT 9..10: 34498..34501
        """
        mppts = []
        total_p_dc = 0.0
        ts_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+07:00"

        # Khối MPPT 1 ~ 8 (33049 ~ 33066: 18 thanh ghi)
        raw_pv1_8 = self._read_input_registers(33049, 18)
        
        # Khối MPPT 9 ~ 10 (34498 ~ 34501: 4 thanh ghi)
        raw_pv9_10 = self._read_input_registers(34498, 4)

        mppt_address_pairs = [
            # MPPT 1..4 (offset 0..7 trong raw_pv1_8)
            (0, 1, raw_pv1_8), (2, 3, raw_pv1_8), (4, 5, raw_pv1_8), (6, 7, raw_pv1_8),
            # MPPT 5..8 (offset 10..17 trong raw_pv1_8, vì offset 8-9 là 33057-33058 Total PV Input Power)
            (10, 11, raw_pv1_8), (12, 13, raw_pv1_8), (14, 15, raw_pv1_8), (16, 17, raw_pv1_8),
            # MPPT 9..10 (offset 0..3 trong raw_pv9_10)
            (0, 1, raw_pv9_10), (2, 3, raw_pv9_10)
        ]

        for i, (v_off, i_off, raw_buf) in enumerate(mppt_address_pairs):
            if raw_buf:
                u_val = self._to_u16(raw_buf, v_off)
                i_val = self._to_u16(raw_buf, i_off)
                
                v_mppt = u_val * 0.1 if u_val is not None else None
                i_mppt = i_val * 0.1 if i_val is not None else None

                if v_mppt == 0.0 or v_mppt is None:
                    i_mppt = 0.0
                    p_mppt = 0.0
                else:
                    p_mppt = round(v_mppt * (i_mppt or 0.0), 2)

                if p_mppt:
                    total_p_dc += p_mppt

                # Mỗi MPPT cấu hình 2 strings (dòng điện mỗi string = i_mppt / 2)
                i_str1 = round((i_mppt or 0.0) / 2.0, 2) if i_mppt is not None else None
                i_str2 = round((i_mppt or 0.0) / 2.0, 2) if i_mppt is not None else None

                mppts.append({
                    "mppt_index": i + 1,
                    "string_on_mppt": 2,
                    "V_mppt": v_mppt,
                    "I_mppt": i_mppt,
                    "P_mppt": p_mppt,
                    "Max_I": None,
                    "Max_V": None,
                    "Max_P": None,
                    "created_at": ts_now,
                    "strings": [
                        {
                            "string_index": i * 2 + 1,
                            "I_mppt": i_str1,
                            "Max_I": None,
                            "created_at": ts_now
                        },
                        {
                            "string_index": i * 2 + 2,
                            "I_mppt": i_str2,
                            "Max_I": None,
                            "created_at": ts_now
                        }
                    ]
                })

        # Tổng công suất PV hệ thống từ thanh ghi 34903~34904 hoặc 33057~33058
        raw_pdc_sys = self._read_input_registers(34903, 2)
        if raw_pdc_sys:
            total_p_dc = float(self._to_s32(raw_pdc_sys, 0))
        elif raw_pv1_8 and len(raw_pv1_8) >= 10:
            total_p_dc = float(self._to_s32(raw_pv1_8, 8))

        return {
            "P_dc": total_p_dc,
            "mppts": mppts
        }

    def read_string(self) -> Dict[str, Any]:
        """Đọc dòng điện chi tiết của 20 chuỗi PV."""
        dc_info = self.read_dc()
        strings = {}
        for mppt in dc_info.get("mppts", []):
            for str_item in mppt.get("strings", []):
                idx = str_item.get("string_index")
                strings[f"string_{idx}_current"] = str_item.get("I_mppt")
        return strings

    # =========================================================
    # 4. ĐO LƯỜNG LƯỚI & METER GIAO NHẬN (GRID / METER DATA 33251~33286)
    # =========================================================

    def read_grid_meter(self) -> Dict[str, Any]:
        """Đọc chuẩn 100% dữ liệu Meter đo đếm phát/nhận lưới tại khối thanh ghi 33251~33286."""
        raw_meter = self._read_input_registers(33251, 36)
        if not raw_meter:
            return {
                "e_import_daily": None, "e_export_daily": None,
                "e_import_total": None, "e_export_total": None,
                "u_a": None, "u_b": None, "u_c": None,
                "i_a": None, "i_b": None, "i_c": None,
                "p_a": None, "p_b": None, "p_c": None,
                "p_grid_total": None, "p_ac_grid_total": None,
                "q_grid_total": None, "s_grid_total": None,
                "pf": None, "f": None
            }

        u_a = self._to_u16(raw_meter, 0) * 0.1 if len(raw_meter) > 0 else None
        i_a = self._to_u16(raw_meter, 1) * 0.01 if len(raw_meter) > 1 else None # 0.01A scale
        u_b = self._to_u16(raw_meter, 2) * 0.1 if len(raw_meter) > 2 else None
        i_b = self._to_u16(raw_meter, 3) * 0.01 if len(raw_meter) > 3 else None
        u_c = self._to_u16(raw_meter, 4) * 0.1 if len(raw_meter) > 4 else None
        i_c = self._to_u16(raw_meter, 5) * 0.01 if len(raw_meter) > 5 else None

        p_a = float(self._to_s32(raw_meter, 6)) if len(raw_meter) >= 8 else None
        p_b = float(self._to_s32(raw_meter, 8)) if len(raw_meter) >= 10 else None
        p_c = float(self._to_s32(raw_meter, 10)) if len(raw_meter) >= 12 else None
        p_grid_total = float(self._to_s32(raw_meter, 12)) if len(raw_meter) >= 14 else None

        q_grid_total = float(self._to_s32(raw_meter, 20)) if len(raw_meter) >= 22 else None # offset 20 (33271)
        s_grid_total = float(self._to_s32(raw_meter, 28)) if len(raw_meter) >= 30 else None # offset 28 (33279)
        pf = self._to_s16(raw_meter, 30) * 0.01 if len(raw_meter) > 30 else None # offset 30 (33281)
        freq = self._to_u16(raw_meter, 31) * 0.01 if len(raw_meter) > 31 else None # offset 31 (33282)

        e_import_total = float(self._to_u32(raw_meter, 32)) * 0.01 if len(raw_meter) >= 34 else None # offset 32 (33283)
        e_export_total = float(self._to_u32(raw_meter, 34)) * 0.01 if len(raw_meter) >= 36 else None # offset 34 (33285)

        return {
            "e_import_daily": None,
            "e_export_daily": None,
            "e_import_total": e_import_total,
            "e_export_total": e_export_total,
            "u_a": u_a,
            "u_b": u_b,
            "u_c": u_c,
            "i_a": i_a,
            "i_b": i_b,
            "i_c": i_c,
            "p_a": p_a,
            "p_b": p_b,
            "p_c": p_c,
            "p_grid_total": p_grid_total,
            "p_ac_grid_total": p_grid_total,
            "q_grid_total": q_grid_total,
            "s_grid_total": s_grid_total,
            "pf": pf,
            "f": freq
        }

    # =========================================================
    # 5. ĐO LƯỜNG PHỤ TẢI (LOAD / BACKUP / SMART LOAD)
    # =========================================================

    def read_load(self) -> Dict[str, Any]:
        raw_l_e = self._read_input_registers(33177, 3)
        e_total = float(self._to_u32(raw_l_e, 0)) if raw_l_e else None
        e_daily = self._to_u16(raw_l_e, 2) * 0.1 if raw_l_e else None

        # Công suất phụ tải nhà (Grid-side Home Load Power): 33147 (Low) + 34343 (High)
        p_load_low = self._read_input_registers(33147, 1)
        p_load_high = self._read_input_registers(34343, 1)
        p_load = None
        if p_load_low:
            low_v = self._to_u16(p_load_low, 0) or 0
            high_v = self._to_u16(p_load_high, 0) if p_load_high else 0
            p_load = float((high_v << 16) | low_v)

        raw_bk1 = self._read_input_registers(33137, 2)
        u_backup_a = self._to_u16(raw_bk1, 0) * 0.1 if raw_bk1 else None
        i_backup_a = self._to_u16(raw_bk1, 1) * 0.1 if raw_bk1 else None

        raw_bk2 = self._read_input_registers(33153, 4)
        u_backup_b = self._to_u16(raw_bk2, 0) * 0.1 if raw_bk2 else None
        i_backup_b = self._to_u16(raw_bk2, 1) * 0.1 if raw_bk2 else None
        u_backup_c = self._to_u16(raw_bk2, 2) * 0.1 if raw_bk2 else None
        i_backup_c = self._to_u16(raw_bk2, 3) * 0.1 if raw_bk2 else None

        raw_p_bk_a = self._read_input_registers(33521, 1)
        raw_p_bk_b = self._read_input_registers(33524, 1)
        raw_p_bk_c = self._read_input_registers(33527, 1)
        p_backup_a = float(self._to_s16(raw_p_bk_a, 0) * 10) if raw_p_bk_a else None
        p_backup_b = float(self._to_s16(raw_p_bk_b, 0) * 10) if raw_p_bk_b else None
        p_backup_c = float(self._to_s16(raw_p_bk_c, 0) * 10) if raw_p_bk_c else None

        raw_bk_s = self._read_input_registers(34613, 2)
        s_backup_load = float(self._to_u32(raw_bk_s, 0)) if raw_bk_s else None

        raw_bk_e_tot = self._read_input_registers(33590, 2)
        e_backup_total = float(self._to_u32(raw_bk_e_tot, 0)) if raw_bk_e_tot else None

        raw_bk_e_day = self._read_input_registers(33596, 1)
        e_backup_daily = self._to_u16(raw_bk_e_day, 0) * 0.1 if raw_bk_e_day else None

        raw_sm_vi = self._read_input_registers(34328, 6)
        u_smart_a = self._to_u16(raw_sm_vi, 0) * 0.1 if raw_sm_vi else None
        u_smart_b = self._to_u16(raw_sm_vi, 1) * 0.1 if raw_sm_vi else None
        u_smart_c = self._to_u16(raw_sm_vi, 2) * 0.1 if raw_sm_vi else None
        i_smart_a = self._to_u16(raw_sm_vi, 3) * 0.1 if raw_sm_vi else None
        i_smart_b = self._to_u16(raw_sm_vi, 4) * 0.1 if raw_sm_vi else None
        i_smart_c = self._to_u16(raw_sm_vi, 5) * 0.1 if raw_sm_vi else None

        raw_sm_p = self._read_input_registers(34391, 3)
        p_smart_a = float(self._to_s16(raw_sm_p, 0) * 10) if raw_sm_p else None
        p_smart_b = float(self._to_s16(raw_sm_p, 1) * 10) if raw_sm_p else None
        p_smart_c = float(self._to_s16(raw_sm_p, 2) * 10) if raw_sm_p else None

        raw_sm_s = self._read_input_registers(34619, 2)
        s_smart_load = float(self._to_u32(raw_sm_s, 0)) if raw_sm_s else None

        raw_sm_e_tot = self._read_input_registers(34411, 2)
        e_smart_total = float(self._to_u32(raw_sm_e_tot, 0)) if raw_sm_e_tot else None

        raw_sm_e_day = self._read_input_registers(34413, 1)
        e_smart_daily = float(self._to_u16(raw_sm_e_day, 0) * 0.1) if raw_sm_e_day else None

        return {
            "e_daily": e_daily,
            "e_total": e_total,
            "p_load": p_load,
            "e_backup_daily": e_backup_daily,
            "e_backup_total": e_backup_total,
            "u_backup_a": u_backup_a,
            "u_backup_b": u_backup_b,
            "u_backup_c": u_backup_c,
            "i_backup_a": i_backup_a,
            "i_backup_b": i_backup_b,
            "i_backup_c": i_backup_c,
            "p_backup_a": p_backup_a,
            "p_backup_b": p_backup_b,
            "p_backup_c": p_backup_c,
            "s_backup_load": s_backup_load,
            "e_smart_daily": e_smart_daily,
            "e_smart_total": e_smart_total,
            "u_smart_a": u_smart_a,
            "u_smart_b": u_smart_b,
            "u_smart_c": u_smart_c,
            "i_smart_a": i_smart_a,
            "i_smart_b": i_smart_b,
            "i_smart_c": i_smart_c,
            "p_smart_a": p_smart_a,
            "p_smart_b": p_smart_b,
            "p_smart_c": p_smart_c,
            "s_smart_load": s_smart_load
        }

    # =========================================================
    # 6. ĐO LƯỜNG PIN LƯU TRỮ (BATTERY / BMS DATA)
    # =========================================================

    def read_battery(self) -> Optional[List[Dict[str, Any]]]:
        """
        Đọc thông số Pin / BMS.
        Ghi chú: 33096 là Lead-Acid Battery Ambient Temperature (Nhiệt độ môi trường pin chì-axit, 0.1°C).
        """
        raw_b1 = self._read_input_registers(33133, 8)
        if not raw_b1:
            return None

        u_val = self._to_u16(raw_b1, 0)
        if not u_val or u_val == 0:
            return None

        batt_u = u_val * 0.1
        batt_i = self._to_s16(raw_b1, 1) * 0.1 if raw_b1 else None
        soc = self._to_u16(raw_b1, 6) if len(raw_b1) > 6 else None
        soh = self._to_u16(raw_b1, 7) if len(raw_b1) > 7 else None

        # Đọc công suất sạc/xả Pin 1 thời gian thực từ 33149~33150 (S32, 1W)
        raw_bp = self._read_input_registers(33149, 2)
        if not raw_bp:
            raw_bp = self._read_input_registers(34905, 2)
        batt_p = float(self._to_s32(raw_bp, 0)) if raw_bp else (round(batt_u * (batt_i or 0.0), 2) if batt_u else None)

        raw_max_i = self._read_input_registers(33041, 1)
        max_i = self._to_u16(raw_max_i, 0) * 0.1 if raw_max_i else None

        raw_lead_temp = self._read_input_registers(33096, 1)
        lead_acid_temp = self._to_s16(raw_lead_temp, 0) * 0.1 if raw_lead_temp else None

        raw_b_e = self._read_input_registers(33161, 8)
        e_charge_total = float(self._to_u32(raw_b_e, 0)) if raw_b_e else None
        e_charge_daily = self._to_u16(raw_b_e, 2) * 0.1 if raw_b_e else None
        e_discharge_total = float(self._to_u32(raw_b_e, 4)) if raw_b_e else None
        e_discharge_daily = self._to_u16(raw_b_e, 6) * 0.1 if raw_b_e else None

        raw_st = self._read_input_registers(33295, 1)
        bms_state_val = self._to_u16(raw_st, 0) if raw_st else None
        bms_state = "NORMAL" if bms_state_val == 0 else f"STATUS_{bms_state_val}"

        raw_cell = self._read_input_registers(34348, 4)
        min_cell_v = self._to_u16(raw_cell, 0) * 0.001 if raw_cell else None
        max_cell_v = self._to_u16(raw_cell, 1) * 0.001 if raw_cell else None
        min_cell_t = self._to_u16(raw_cell, 2) * 0.1 if raw_cell else None
        max_cell_t = self._to_u16(raw_cell, 3) * 0.1 if raw_cell else None

        raw_lim = self._read_holding_registers(43011, 1)
        discharge_v_limit = self._to_u16(raw_lim, 0) * 1.0 if raw_lim else None # %

        info = self.read_info()
        batt_sn = f"BATT_{info.get('serial_number', 'SOLIS')}_1"

        battery_item = {
            "serial_number": batt_sn,
            "cycle_count": None,
            "e_charge_daily": e_charge_daily,
            "e_discharge_daily": e_discharge_daily,
            "e_charge_total": e_charge_total,
            "e_discharge_total": e_discharge_total,
            "inv_batt_u": batt_u,
            "inv_batt_i": batt_i,
            "inv_batt_p": batt_p,
            "bms_batt_u": batt_u,
            "bms_batt_i": batt_i,
            "bms_batt_p": batt_p,
            "bms_batt_soc": soc,
            "bms_batt_soh": soh,
            "bms_max_charge_i": max_i,
            "bms_max_discharge_i": max_i,
            "bms_discharge_volt_limit": discharge_v_limit,
            "bms_state": bms_state,
            "bms_min_cell_volt": min_cell_v,
            "bms_max_cell_volt": max_cell_v,
            "bms_min_cell_temp": min_cell_t,
            "bms_max_cell_temp": max_cell_t
        }

        battery_list = [battery_item]

        # Đọc Battery 2 (Slave Battery / Cổng Pin 2) nếu có kết nối
        raw_b2_u = self._read_input_registers(34289, 2)
        raw_b2_soc = self._read_input_registers(34277, 6)
        raw_b2_p = self._read_input_registers(34368, 2)

        u2_val = self._to_u16(raw_b2_u, 0) if raw_b2_u else 0
        soc2_val = self._to_u16(raw_b2_soc, 1) if raw_b2_soc else None

        if u2_val and u2_val > 0:
            batt2_u = u2_val * 0.1
            batt2_i = self._to_s16(raw_b2_u, 1) * 0.1 if len(raw_b2_u) > 1 else None
            batt2_p = float(self._to_s32(raw_b2_p, 0)) if raw_b2_p else (round(batt2_u * (batt2_i or 0.0), 2) if batt2_u else None)
            batt2_soc = soc2_val
            batt2_soh = self._to_u16(raw_b2_soc, 2) if len(raw_b2_soc) > 2 else None
            batt2_temp = self._to_s16(raw_b2_soc, 0) * 0.1 if len(raw_b2_soc) > 0 else None
            batt2_chg_i = self._to_u16(raw_b2_soc, 4) * 0.1 if len(raw_b2_soc) > 4 else max_i
            batt2_dis_i = self._to_u16(raw_b2_soc, 5) * 0.1 if len(raw_b2_soc) > 5 else max_i
            
            raw_b2_dis_v = self._read_input_registers(34371, 1)
            batt2_dis_v = self._to_u16(raw_b2_dis_v, 0) * 0.1 if raw_b2_dis_v else discharge_v_limit

            batt2_sn = f"BATT_{info.get('serial_number', 'SOLIS')}_2"
            battery_list.append({
                "serial_number": batt2_sn,
                "cycle_count": None,
                "e_charge_daily": e_charge_daily,
                "e_discharge_daily": e_discharge_daily,
                "e_charge_total": e_charge_total,
                "e_discharge_total": e_discharge_total,
                "inv_batt_u": batt2_u,
                "inv_batt_i": batt2_i,
                "inv_batt_p": batt2_p,
                "bms_batt_u": batt2_u,
                "bms_batt_i": batt2_i,
                "bms_batt_p": batt2_p,
                "bms_batt_soc": batt2_soc,
                "bms_batt_soh": batt2_soh,
                "bms_max_charge_i": batt2_chg_i,
                "bms_max_discharge_i": batt2_dis_i,
                "bms_discharge_volt_limit": batt2_dis_v,
                "bms_state": "NORMAL",
                "bms_min_cell_volt": None,
                "bms_max_cell_volt": None,
                "bms_min_cell_temp": batt2_temp,
                "bms_max_cell_temp": batt2_temp
            })

        return battery_list

    # =========================================================
    # 7. TRẠNG THÁI & MÃ LỖI (ERRORS / FAULTS CHUẨN APPENDIX 3 & 4)
    # =========================================================

    def read_errors(self) -> List[Dict[str, Any]]:
        """
        Đọc mã lỗi & cảnh báo từ thanh ghi 33095 (Main Code) và 33070 (Sub Code)
        Dựa trên Phụ lục 3 (Appendix 3 / Table 108) của tài liệu Solis Hybrid.
        """
        raw_main = self._read_input_registers(33095, 1)
        raw_sub = self._read_input_registers(33070, 1)

        main_code = self._to_u16(raw_main, 0) if raw_main else 0
        sub_code = self._to_u16(raw_sub, 0) if raw_sub else 0

        # Từ điển diễn giải mã lỗi chính từ Appendix 3 (Table 108)
        fault_map = {
            0xF010: "Surge Alarm - Electric surge protection triggered",
            0xF011: "Fan Alarm - Internal cooling fan failure",
            0xF013: "VgSpdFail - AC Surge Protection Device failure",
            0xF014: "DcSpdFail - DC Surge Protection Device failure",
            0xF015: "Fan_H Alarm - External heatsink fan failure",
            0xF016: "FuseFail - Fuse abnormality",
            0xF017: "L&PE FAIL - Phase-PE grounding fault",
            0xF019: "BoostFail - DC-DC Boost circuit failure",
            0xF01A: "Gen_Start_Fail - Generator start failed",
            0xF01B: "Gen_Stop_Fail - Generator stop failed",
            0xF01C: "IGBT TEMP DIF - Excessive IGBT temperature difference",
            0xF01D: "N-PE V fault - Neutral-PE voltage fault",
            0xF01E: "PV-Batt-Mismatch - PV and Battery power mismatch",
            0xF01F: "Gen-Phase-Err - Generator voltage phase error",
            0xF020: "BMS_ALARM(WARN)01 - Battery BMS Warning 01",
            0xF021: "BMS_ALARM(WARN)02 - Battery BMS Warning 02",
            0xF022: "BMS_ALARM(WARN)03 - Battery BMS Warning 03",
            0xF023: "BMS_ALARM(WARN)04 - Battery BMS Warning 04",
            0xF024: "BMS_ALARM(WARN)05 - Battery BMS Warning 05",
            0xF025: "BMS_ALARM(WARN)06 - Battery BMS Warning 06",
        }

        faults = []
        if main_code and main_code >= 0xF000:
            desc = fault_map.get(main_code, f"Solis Fault Code 0x{main_code:04X} (Sub: 0x{sub_code:04X})")
            faults.append({
                "fault_code": main_code,
                "fault_description": desc,
                "repair_instruction": "Check inverter manual Appendix 3",
                "severity": "ERROR" if main_code >= 0xF010 else "WARNING"
            })

        if not faults:
            faults.append({
                "fault_code": 0,
                "fault_description": "NORMAL",
                "repair_instruction": "",
                "severity": "STABLE"
            })

        return faults

    def read_states_and_faults(self) -> Dict[str, Any]:
        """
        Đọc trạng thái vận hành và danh sách mã lỗi.
        Thanh ghi 33121 (Appendix 4 Bitfield): BIT00 (Normal Operation), BIT01 (Grid-tied), BIT02 (Charging), BIT03 (Discharging), BIT04 (Has Alarm).
        Thanh ghi 33095: Inverter Current Status Code (0=Waiting, 1=OpenRun, 2=SoftRun, 3=Generating, 4=Off-Grid).
        """
        raw_op = self._read_input_registers(33121, 1)
        raw_status = self._read_input_registers(33095, 1)

        op_val = self._to_u16(raw_op, 0) if raw_op else 0
        status_code = self._to_u16(raw_status, 0) if raw_status else 0

        status_text_map = {
            0x0000: "Waiting",
            0x0001: "OpenRun",
            0x0002: "SoftRun",
            0x0003: "Generating (Grid-tied)",
            0x0004: "Off-Grid",
        }

        inv_status_str = status_text_map.get(status_code, f"Status_0x{status_code:04X}")
        is_normal = bool(op_val & 0x0001) if raw_op else True
        has_alarm = bool(op_val & 0x0010) if raw_op else False

        errors = self.read_errors()

        return {
            "state": "ERROR" if has_alarm or (errors and errors[0].get("fault_code", 0) != 0) else "STABLE",
            "operating_status_raw": op_val,
            "inverter_status_text": inv_status_str,
            "is_normal": is_normal,
            "faults": errors
        }

    def parse(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Triển khai interface BaseDriver parse."""
        return raw_data

    def read_all(self) -> Dict[str, Any]:
        """Triển khai interface BaseDriver read_all (trả về cả cấu trúc nested và key phẳng)."""
        info_data = self.read_info() or {}
        ac_data = self.read_ac() or {}
        dc_data = self.read_dc() or {}
        grid_data = self.read_grid_meter() or {}
        load_data = self.read_load() or {}
        battery_data = self.read_battery() or []
        errors_data = self.read_errors() or []

        res = {
            "info": info_data,
            "ac": ac_data,
            "dc": dc_data,
            "grid": grid_data,
            "load": load_data,
            "battery": battery_data,
            "errors": errors_data,

            # Key phẳng tiêu chuẩn cho PollingService & CacheDB & NormalizationService:
            "v_a": ac_data.get("V_a"),
            "v_b": ac_data.get("V_b"),
            "v_c": ac_data.get("V_c"),
            "i_a": ac_data.get("I_a"),
            "i_b": ac_data.get("I_b"),
            "i_c": ac_data.get("I_c"),
            "p_inv_w": ac_data.get("P_ac"),
            "q_inv_var": ac_data.get("Q_ac"),
            "pf": ac_data.get("PF"),
            "grid_hz": ac_data.get("H"),
            "temp_c": ac_data.get("Temp_C"),
            "e_daily": ac_data.get("E_daily"),
            "e_total": ac_data.get("E_total"),
            "ir": ac_data.get("IR"),
            "p_dc_w": dc_data.get("P_dc"),
        }

        # Phẳng hóa MPPT và Strings
        mppts = dc_data.get("mppts", [])
        for mppt in mppts:
            m_idx = mppt.get("mppt_index")
            if m_idx:
                res[f"mppt_{m_idx}_voltage"] = mppt.get("V_mppt")
                res[f"mppt_{m_idx}_current"] = mppt.get("I_mppt")
            for str_item in mppt.get("strings", []):
                s_idx = str_item.get("string_index")
                if s_idx:
                    res[f"string_{s_idx}_current"] = str_item.get("I_mppt")

        # Phẳng hóa Battery (Pin 1)
        if isinstance(battery_data, list) and len(battery_data) > 0:
            b0 = battery_data[0]
            res["bms_batt_soc"] = b0.get("bms_batt_soc")
            res["bms_batt_soh"] = b0.get("bms_batt_soh")
            res["inv_batt_u"] = b0.get("inv_batt_u")
            res["inv_batt_i"] = b0.get("inv_batt_i")
            res["inv_batt_p"] = b0.get("inv_batt_p")
            res["e_charge_daily"] = b0.get("e_charge_daily")
            res["e_discharge_daily"] = b0.get("e_discharge_daily")
            res["e_charge_total"] = b0.get("e_charge_total")
            res["e_discharge_total"] = b0.get("e_discharge_total")
            res["bms_min_cell_temp"] = b0.get("bms_min_cell_temp")
            res["bms_max_cell_temp"] = b0.get("bms_max_cell_temp")
        elif isinstance(battery_data, dict):
            res["bms_batt_soc"] = battery_data.get("bms_batt_soc")
            res["bms_batt_soh"] = battery_data.get("bms_batt_soh")
            res["inv_batt_u"] = battery_data.get("inv_batt_u")
            res["inv_batt_i"] = battery_data.get("inv_batt_i")
            res["inv_batt_p"] = battery_data.get("inv_batt_p")

        if isinstance(info_data, dict):
            res["serial_number"] = info_data.get("serial_number")
            res["brand"] = "Solis"
            res["model"] = "S6-EH3P99.9K10-NV-YD-H"
            res["mppt_count"] = info_data.get("mppt_count", 10)
            res["string_count"] = info_data.get("string_count", 20)
            res["is_active"] = info_data.get("is_active", True)

        if errors_data and isinstance(errors_data, list) and len(errors_data) > 0:
            res["fault_code"] = errors_data[0].get("fault_code", 0)

        return res

    # =========================================================
    # 8. ĐIỀU KHIỂN & GIỚI HẠN CÔNG SUẤT (POWER LIMIT CONTROL CHUẨN DOCX)
    # =========================================================

    def enable_power_limit(self, enable: bool) -> bool:
        """
        Bật / Tắt chế độ điều khiển công suất từ xa qua thanh ghi holding 43132.
        Val = 2: Enable Remote Active Power Regulation.
        Val = 0: Off.
        """
        val = 2 if enable else 0
        if self.transport and hasattr(self.transport, "write_register"):
            try:
                res = self.transport.write_register(43132, val, slave=self.slave_id)
                return not (hasattr(res, "isError") and res.isError())
            except Exception as e:
                logger.error(f"Failed to enable power limit (43132): {e}")
        return False

    def write_power_limit_kw(self, kw: float) -> bool:
        """
        Ghi giới hạn công suất phát lưới (kW) vào thanh ghi holding 43128 (đơn vị 10W, dải 0~300kW).
        Ví dụ: 50kW = 5000 (10W scale).
        Tự động bật chế độ Remote Regulation tại 43132 nếu chưa bật.
        """
        self.enable_power_limit(True)
        w_val = int(kw * 100) # 10W scale (ví dụ 99.9kW -> 9990)
        if self.transport and hasattr(self.transport, "write_register"):
            try:
                res = self.transport.write_register(43128, w_val, slave=self.slave_id)
                return not (hasattr(res, "isError") and res.isError())
            except Exception as e:
                logger.error(f"Failed to write power limit kW (43128): {e}")
        return False

    def write_power_limit_percent(self, percent: float) -> bool:
        """Ghi giới hạn công suất % (0 ~ 100%). Dựa trên công suất định mức 99.9kW."""
        kw = (percent / 100.0) * 99.9
        return self.write_power_limit_kw(kw)

    def read_power_limit_percent(self) -> float:
        """Đọc lại giới hạn công suất % từ holding register 43128."""
        raw = self._read_holding_registers(43128, 1)
        if raw:
            w_val = self._to_u16(raw, 0)
            if w_val is not None:
                kw = w_val / 100.0
                return round((kw / 99.9) * 100.0, 1)
        return 100.0

    # =========================================================
    # 9. BUILD TELEMETRY V2 PAYLOAD COMPLETE
    # =========================================================

    def build_telemetry_v2_payload(self, e_monthly_calc: Optional[float] = None) -> Dict[str, Any]:
        """
        Đóng gói hoàn chỉnh bản tin Telemetry V2 cho hệ Solis Hybrid 99.9kW.
        Đầy đủ 5 khối: project, inverters, grid, load, batteries.
        """
        ts_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+07:00"

        info = self.read_info()
        ac_data = self.read_ac()
        dc_data = self.read_dc()
        grid_data = self.read_grid_meter()
        load_data = self.read_load()
        batt_data = self.read_battery()
        errors_data = self.read_errors()

        if not grid_data.get("u_a") or grid_data.get("u_a") == 0:
            grid_data["u_a"] = ac_data.get("V_a")
            grid_data["u_b"] = ac_data.get("V_b")
            grid_data["u_c"] = ac_data.get("V_c")

        if not grid_data.get("i_a") or grid_data.get("i_a") == 0:
            grid_data["i_a"] = ac_data.get("I_a")
            grid_data["i_b"] = ac_data.get("I_b")
            grid_data["i_c"] = ac_data.get("I_c")

        if not grid_data.get("f") or grid_data.get("f") == 0:
            grid_data["f"] = ac_data.get("H")

        ac_data["created_at"] = ts_now
        ac_data["E_monthly"] = e_monthly_calc

        grid_data["created_at"] = ts_now
        load_data["created_at"] = ts_now

        if batt_data:
            for b in batt_data:
                b["created_at"] = ts_now

        for err in errors_data:
            err["created_at"] = ts_now

        inverter_obj = {
            "serial_number": info.get("serial_number", "UNKNOWN_SN"),
            "ac": ac_data,
            "mppts": dc_data.get("mppts", []),
            "errors": errors_data
        }

        project_obj = {
            "Temp_C": ac_data.get("Temp_C"),
            "P_ac": ac_data.get("P_ac", 0.0),
            "P_dc": dc_data.get("P_dc", 0.0),
            "E_daily": ac_data.get("E_daily", 0.0),
            "E_monthly": e_monthly_calc,
            "E_total": ac_data.get("E_total", 0.0),
            "severity": errors_data[0].get("severity", "STABLE") if errors_data else "STABLE",
            "created_at": ts_now
        }

        payload = {
            "project": project_obj,
            "inverters": [inverter_obj],
            "grid": grid_data,
            "load": load_data,
            "batteries": batt_data
        }

        return payload


# Aliases cho dynamic driver loader
Soliss6eh3p999k10nvydh = SolisS6HybridDriver
SolisS6EH3P999K10NVYDH = SolisS6HybridDriver
