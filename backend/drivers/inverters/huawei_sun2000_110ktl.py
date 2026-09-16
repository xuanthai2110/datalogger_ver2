# drivers/huawei_sun2000_110ktl.py

from typing import Dict, Any
from backend.drivers.inverters.base import BaseDriver

class Huaweisun2000110ktl(BaseDriver):

    def __init__(self, transport, slave_id=1):
        self.transport = transport
        self.slave_id = slave_id

    # =========================================================
    # ================= REGISTER MAP ==========================
    # =========================================================

    def register_map(self) -> Dict[str, Any]:

        return {

            "info": [
                {"name": "serial_number", "address": 30015, "length": 10, "type": "string", "scale": None},
                {"name": "string_count", "address": 30071, "length": 1, "type": "uint16", "scale": None},
                {"name": "mppt_count", "address": 30072, "length": 1, "type": "uint16", "scale": None},
                {"name": "rate_dc_kwp", "address": 30073, "length": 2, "type": "uint32", "scale": 0.001},
                {"name": "rate_ac_kw", "address": 30075, "length": 2, "type": "uint32", "scale": 0.001},
            ],

            "ac": [
                {"name": "v_a", "address": 32069, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_b", "address": 32070, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_c", "address": 32071, "length": 1, "type": "uint16", "scale": 0.1},

                {"name": "i_a", "address": 32072, "length": 2, "type": "sint32", "scale": 0.001},    
                {"name": "i_b", "address": 32074, "length": 2, "type": "sint32", "scale": 0.001},
                {"name": "i_c", "address": 32076, "length": 2, "type": "sint32", "scale": 0.001},

                {"name": "p_inv_w", "address": 32080, "length": 2, "type": "sint32", "scale": 1},
                {"name": "q_inv_var", "address": 32082, "length": 2, "type": "sint32", "scale": 1},
                {"name": "pf", "address": 32084, "length": 1, "type": "sint16", "scale": 0.001},
                {"name": "grid_hz", "address": 32085, "length": 1, "type": "uint16", "scale": 0.01},
            ],

            "dc": [
                {"name": "p_dc_w", "address": 32064, "length": 2, "type": "uint32", "scale": 1},

                {"name": "mppt_1_voltage", "address": 32016, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_2_voltage", "address": 32018, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_3_voltage", "address": 32020, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_4_voltage", "address": 32022, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_5_voltage", "address": 32024, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_6_voltage", "address": 32026, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_7_voltage", "address": 32028, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_8_voltage", "address": 32030, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_9_voltage", "address": 32032, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_10_voltage", "address": 32034, "length": 1, "type": "sint16", "scale": 0.1},
            ],

            "string": [
                {
                    "name": f"string_{i}_current",
                    "address": 32017 + (i - 1) * 2,
                    "length": 1,
                    "type": "sint16",
                    "scale": 0.01
                }
                for i in range(1, 21)
            ],

            "stat": [
                # Nhiệt độ bộ tản nhiệt inverter (C)
                {"name": "temp_c",   "address": 32087, "length": 1, "type": "sint16", "scale": 0.1},
                # Điện trở cách điện PV (Ω)
                {"name": "ir",       "address": 32088, "length": 1, "type": "uint16", "scale": 1},
                # Sản lượng ngày (kWh)
                {"name": "e_daily",  "address": 32114, "length": 2, "type": "uint32", "scale": 0.01},
                # Sản lượng tổng (kWh)
                {"name": "e_total",  "address": 32106, "length": 2, "type": "uint32", "scale": 0.01},
            ],
            "control": [
                {"name": "p_set_kw","address": 40120,"length": 1,"type": "uint16","scale": 0.1},
                {"name": "p_set_percent","address": 40125,"length": 1,"type": "uint16","scale": 0.1},       
                {"name": "p_set_w","address": 40126,"length": 2,"type": "uint32","scale": 1      },
                {"name": "power_factor","address": 40122,"length": 1,"type": "sint16","scale": 0.001 },
                {"name": "q_over_s","address": 40123,"length": 1,"type": "sint16","scale": 0.001},
                {"name": "q_set_var","address": 40129,"length": 2,"type": "sint32","scale": 1 }
            ]

        }

    # =========================================================
    # ================= MODBUS READ ===========================
    # =========================================================

    def _read_block(self, start: int, length: int):

        response = self.transport.read_holding_registers(
            address=start,
            count=length,
            slave=self.slave_id
        )

        if response.isError():
            raise Exception("Modbus read error")

        return response.registers

    # =========================================================
    # ================= PARSER ================================
    # =========================================================

    def _convert(self, registers, data_type):

        if not registers:
            return None

        if data_type == "uint16":
            return registers[0] & 0xFFFF

        if data_type == "sint16":
            v = registers[0] & 0xFFFF
            if v & 0x8000:
                v -= 0x10000
            return v

        # Huawei word order: high word first

        if data_type == "uint32":
            high = registers[0]
            low = registers[1]
            return ((high & 0xFFFF) << 16) | (low & 0xFFFF)

        if data_type == "sint32":
            high = registers[0]
            low = registers[1]

            v = ((high & 0xFFFF) << 16) | (low & 0xFFFF)

            if v & 0x80000000:
                v -= 0x100000000

            return v

        if data_type == "string":

            raw_bytes = bytearray()

            for reg in registers:
                high = (reg >> 8) & 0xFF
                low = reg & 0xFF
                raw_bytes.append(high)
                raw_bytes.append(low)

            return raw_bytes.decode("utf-8", errors="ignore").rstrip("\x00").strip()

        return None

    # =========================================================
    # ================= PARSE BLOCK ===========================
    # =========================================================

    def parse(self, raw_block: Dict[str, Any], reg_list: list = None) -> Dict[str, Any]:
        """ Implement base parsing compatibility. The original API takes block and list. """
        if reg_list is None:
            return {}

        result = {}
        offset = 0

        for reg in reg_list:

            length = reg["length"]

            raw = raw_block[offset: offset + length]

            value = self._convert(raw, reg["type"])

            if value is not None and reg["scale"] is not None:
                value *= reg["scale"]

            result[reg["name"]] = value

            offset += length

        return result

    # =========================================================
    # ================= READ GROUPS ===========================
    # =========================================================

    def read_info(self) -> Dict[str, Any]:
        from datetime import datetime
        try:
            regs = self.register_map()["info"]

            start = min(r["address"] for r in regs)
            end = max(r["address"] + r["length"] - 1 for r in regs)

            raw = self._read_block(start, end - start + 1)

            ordered = []

            for r in regs:
                idx = r["address"] - start
                ordered.extend(raw[idx: idx + r["length"]])

            parsed = self.parse(ordered, regs)

            mppt_count = int(parsed.get("mppt_count", 10))
            string_count = int(parsed.get("string_count", 20))
            if mppt_count <= 0:
                mppt_count = 10
            if string_count <= 0:
                string_count = 20
            strings_per_mppt = string_count // mppt_count

            rate_dc = parsed.get("rate_dc_kwp", 110.0)
            rate_ac = parsed.get("rate_ac_kw", 110.0)

            return {
                "brand": "Huawei",
                "model": "SUN2000-110KTL",
                "serial_number": parsed.get("serial_number", ""),
                "capacity_kw": rate_ac,
                "mppt_count": mppt_count,
                "firmware_version": "1.0",
                "phase_count": 3,
                "strings_per_mppt": strings_per_mppt,
                "string_count": string_count,
                "rate_dc_kwp": rate_dc,
                "rate_ac_kw": rate_ac,
                "is_active": True,
                "slave_id": self.slave_id,
                "usage_start_at": datetime.now().isoformat(),
                "usage_end_at": None,
                "replaced_by_id": None
            }
        except Exception as e:
            return {
                "brand": "Huawei",
                "model": "SUN2000-110KTL",
                "serial_number": "",
                "capacity_kw": 110.0,
                "mppt_count": 10,
                "firmware_version": "1.0",
                "phase_count": 3,
                "strings_per_mppt": 2,
                "string_count": 20,
                "rate_dc_kwp": 110.0,
                "rate_ac_kw": 110.0,
                "is_active": False,
                "slave_id": self.slave_id,
                "usage_start_at": datetime.now().isoformat(),
                "usage_end_at": None,
                "replaced_by_id": None
            }

    def read_ac(self) -> Dict[str, Any]:

        regs = self.register_map()["ac"]

        start = min(r["address"] for r in regs)
        end = max(r["address"] + r["length"] - 1 for r in regs)

        raw = self._read_block(start, end - start + 1)

        ordered = []

        for r in regs:
            idx = r["address"] - start
            ordered.extend(raw[idx: idx + r["length"]])

        return self.parse(ordered, regs)

    def read_dc(self) -> Dict[str, Any]:

        regs = self.register_map()["dc"]

        start = min(r["address"] for r in regs)
        end = max(r["address"] + r["length"] - 1 for r in regs)

        raw = self._read_block(start, end - start + 1)

        ordered = []

        for r in regs:
            idx = r["address"] - start
            ordered.extend(raw[idx: idx + r["length"]])

        return self.parse(ordered, regs)

    def read_string(self) -> Dict[str, Any]:

        regs = self.register_map()["string"]

        start = regs[0]["address"]
        end = regs[-1]["address"]

        raw = self._read_block(start, end - start + 1)

        result = {}

        for r in regs:

            idx = r["address"] - start
            val = self._convert([raw[idx]], r["type"])

            if val is not None:
                val *= r["scale"]

            result[r["name"]] = val

        return result

    def read_stat(self) -> Dict[str, Any]:
        """Đọc thống kê vận hành: nhiệt độ, điện trở cách điện, sản lượng ngày và tổng."""
        regs  = self.register_map()["stat"]
        start = min(r["address"] for r in regs)
        end   = max(r["address"] + r["length"] - 1 for r in regs)
        raw   = self._read_block(start, end - start + 1)
        ordered = []
        for r in regs:
            idx = r["address"] - start
            ordered.extend(raw[idx: idx + r["length"]])
        return self.parse(ordered, regs)

    # =========================================================
    # ================= FAULTS & STATES =======================
    # =========================================================

    def read_states_and_faults(self) -> Dict[str, Any]:
        """
        Đọc trạng thái và lỗi thô từ inverter Huawei:
        - Thanh ghi 32089 (Device Status)
        - Thanh ghi 32008-32010 (Alarm Bitmasks 1, 2, 3)
        """
        ALARM_1_BITS = {
            0: 2001, 1: 2002, 2: 2011, 3: 2012, 4: 2013, 5: 2021, 6: 2031, 
            7: 2032, 8: 2033, 9: 2034, 10: 2035, 11: 2036, 12: 2037, 13: 2038, 
            14: 2039, 15: 2040
        }
        ALARM_2_BITS = {
            0: 2051, 1: 2061, 2: 2062, 3: 2063, 4: 2064, 5: 2065, 6: 2066, 
            7: 61440, 8: 2067, 9: 2068, 10: 2070, 11: 2071, 12: 2072, 13: 2075, 
            14: 2077, 15: 2080
        }
        ALARM_3_BITS = {
            0: 2081, 1: 2085, 2: 2014, 3: 2086, 4: 2069, 5: 2082, 6: 2015, 
            7: 2087, 8: 2088, 9: 2089, 10: 2090, 11: 2091, 12: 2092, 13: 2003, 
            14: 2093, 15: 2094
        }

        # 1. Đọc Device Status (32089)
        res_state = self.transport.read_holding_registers(
            address=32089,
            count=1,
            slave=self.slave_id
        )
        state_id = 0
        if not res_state.isError():
            state_id = res_state.registers[0]

        # 2. Đọc Alarms (32008 - 32010)
        res_fault = self.transport.read_holding_registers(
            address=32008,
            count=3,
            slave=self.slave_id
        )
        fault_code = 0
        active_faults = []
        if not res_fault.isError():
            alarm_1, alarm_2, alarm_3 = res_fault.registers
            
            # Quét Alarm 1
            for bit, alarm_id in ALARM_1_BITS.items():
                if (alarm_1 >> bit) & 1:
                    active_faults.append(alarm_id)
            
            # Quét Alarm 2
            for bit, alarm_id in ALARM_2_BITS.items():
                if (alarm_2 >> bit) & 1:
                    active_faults.append(alarm_id)
            
            # Quét Alarm 3
            for bit, alarm_id in ALARM_3_BITS.items():
                if (alarm_3 >> bit) & 1:
                    active_faults.append(alarm_id)
                    
            if active_faults:
                fault_code = active_faults[0]

        return {
            "state_id": state_id,
            "fault_code": fault_code,
            "active_faults": active_faults
        }


    # =========================================================
    # ================= READ ALL ==============================
    # =========================================================

    def read_all(self) -> Dict[str, Any]:
        import json
        data = {}

        data.update(self.read_info())
        data.update(self.read_ac())

        dc = self.read_dc()
        strings = self.read_string()

        data.update(dc)
        data.update(strings)

        # Đọc thống kê: nhiệt độ, IR, sản lượng ngày/tổng
        try:
            data.update(self.read_stat())
        except Exception:
            pass

        # calculate MPPT current
        for i in range(1, 11):
            s1 = strings.get(f"string_{2*i-1}_current")
            s2 = strings.get(f"string_{2*i}_current")
            if s1 is not None and s2 is not None:
                data[f"mppt_{i}_current"] = s1 + s2

        # Đọc trạng thái và lỗi
        try:
            states_and_faults = self.read_states_and_faults()
            data.update(states_and_faults)
        except Exception:
            pass

        return data


    # =========================================================
    # ================= CONTROL ===============================
    # =========================================================

    def enable_power_limit(self, enable: bool) -> bool:
        # Tạm thời chưa có địa chỉ cho enable limit riêng trên Huawei
        return True

    def write_power_limit_kw(self, kw: float) -> bool:
        return self.set_power_kw(kw)

    def write_power_limit_percent(self, percent: float) -> bool:
        return self.set_power_percent(percent)


    @staticmethod
    def _ensure_write_ok(response, action: str) -> bool:
        if response is None:
            raise Exception(f"{action} returned no response")
        if hasattr(response, "isError") and response.isError():
            raise Exception(f"{action} failed: {response}")
        return True

    def set_power_percent(self, percent):

        addr = 40125

        value = int(percent * 10)

        response = self.transport.write_register(
            address=addr,
            value=value,
            slave=self.slave_id
        )

        return self._ensure_write_ok(response, f"Write percent limit {percent}")


    # --------------------------------
    # Set power limit by kW
    # --------------------------------
    def set_power_kw(self, kw):

        addr = 40120

        value = int(kw * 10)

        response = self.transport.write_register(
            address=addr,
            value=value,
            slave=self.slave_id
        )

        return self._ensure_write_ok(response, f"Write kW limit {kw}")


    # --------------------------------
    # Set power limit by W
    # --------------------------------
    def set_power_w(self, watt):

        addr = 40126

        watt = int(round(watt))

        high = (watt >> 16) & 0xFFFF
        low = watt & 0xFFFF

        # Thay vì viết thuần pymodbus, ta sử dụng method write_multiple_registers của communication ModbusTCP
        response = self.transport.write_multiple_registers(
            address=addr,
            values=[high, low],
            slave=self.slave_id
        )

        return self._ensure_write_ok(response, f"Write watt limit {watt}")


    # --------------------------------
    # Read power limit
    # --------------------------------
    def read_power_limit(self):

        # Huawei requires 35300-35303 to be read as a single block.
        # Otherwise, reading individually may cause Exception 131 IllegalValue.
        res = self.transport.read_holding_registers(
            address=35300,
            count=4,
            slave=self.slave_id
        )

        if res.isError():
            raise Exception(f"Read power limit failed: {res}")

        regs = res.registers

        # 35300 (Mode)
        mode = regs[0]

        # 35302, 35303 (Active power limit)
        limit_w = (regs[2] << 16) + regs[3]

        return {
            "mode": mode,
            "limit_w": limit_w
        }

    # --------------------------------
    # Read actual inverter power
    # --------------------------------
    def read_power(self):

        res = self.transport.read_holding_registers(
            address=32080,
            count=2,
            slave=self.slave_id
        )

        if res.isError():
            raise Exception(f"Read inverter power failed: {res}")

        regs = res.registers

        value = (regs[0] << 16) + regs[1]

        if value > 0x7FFFFFFF:
            value -= 0x100000000

        return value

    def read_power_limit_percent(self) -> float:
        try:
            res = self.transport.read_holding_registers(
                address=40125,
                count=1,
                slave=self.slave_id,
            )
            if res.isError() or not res.registers:
                return 100.0
            return float(res.registers[0]) / 10.0
        except Exception:
            return 100.0
