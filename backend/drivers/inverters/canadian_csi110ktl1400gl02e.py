# drivers/canadian_csi110ktl1400gl02e.py

from typing import Dict, Any
from backend.drivers.inverters.base import BaseDriver


class Canadiancsi110ktl1400gl02e(BaseDriver):
    def __init__(self, transport, slave_id: int = 1):
        self.transport = transport
        self.slave_id = slave_id

    # =========================================================
    # ================= REGISTER MAP ==========================
    # =========================================================

    def register_map(self) -> Dict[str, Any]:
        return {
            "info": [
                {"name": "serial_number", "address": 0x0B07, "length": 10, "type": "string", "scale": None},
                {"name": "rated_power", "address": 0x090C, "length": 1, "type": "uint16", "scale": 1.0},
                {"name": "dsp_version", "address": 0x0B02, "length": 1, "type": "uint16", "scale": 1.0},
                {"name": "arm_version", "address": 0x0B03, "length": 1, "type": "uint16", "scale": 1.0},
            ],
            "ac": [
                {"name": "v_a", "address": 0x810F, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_b", "address": 0x8110, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_c", "address": 0x8111, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "i_a", "address": 0x8100, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "i_b", "address": 0x8101, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "i_c", "address": 0x8102, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "p_inv_w", "address": 0x8106, "length": 1, "type": "sint16", "scale": 100.0},
                {"name": "q_inv_var", "address": 0x810A, "length": 1, "type": "sint16", "scale": 100.0},
                {"name": "pf", "address": 0x810E, "length": 1, "type": "sint16", "scale": 0.01},
                {"name": "grid_hz", "address": 0x800B, "length": 1, "type": "uint16", "scale": 0.1},
            ],
            "dc": [
                {"name": "p_dc_w", "address": 0x8201, "length": 1, "type": "sint16", "scale": 100.0},
                {"name": "mppt_1_voltage", "address": 0x8202, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_2_voltage", "address": 0x8206, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_3_voltage", "address": 0x820A, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_4_voltage", "address": 0x820E, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_5_voltage", "address": 0x8212, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_6_voltage", "address": 0x8216, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_7_voltage", "address": 0x821A, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_8_voltage", "address": 0x821E, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_9_voltage", "address": 0x8222, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_10_voltage", "address": 0x8226, "length": 1, "type": "uint16", "scale": 0.1},
            ],
            "string": [
                {
                    "name": f"string_{i}_current",
                    "address": 0x8203 + (i - 1) * 2,
                    "length": 1,
                    "type": "sint16",
                    "scale": 0.1,
                }
                for i in range(1, 21)
            ],
            "stat": [
                {"name": "temp_c", "address": 0x8301, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "ir", "address": 0x8306, "length": 1, "type": "uint16", "scale": 1.0},
                {"name": "e_daily", "address": 0x8013, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "e_total", "address": 0x8015, "length": 2, "type": "uint32", "scale": 1.0},
            ],
            "control": [
                {"name": "active_power_mode", "address": 0x0602, "length": 1, "type": "uint16", "scale": None},
                {"name": "local_power_limit_kw", "address": 0x0524, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "remote_power_limit_percent", "address": 0x0708, "length": 1, "type": "sint16", "scale": 0.1},
            ],
        }

    # =========================================================
    # ================= LOW LEVEL READ ========================
    # =========================================================

    def _read_input(self, start: int, length: int):
        response = self.transport.read_input_registers(
            address=start,
            count=length,
            slave=self.slave_id,
        )
        if response.isError():
            raise Exception(f"Modbus read_input_registers error at {start}")
        return response.registers

    def _read_holding(self, start: int, length: int):
        response = self.transport.read_holding_registers(
            address=start,
            count=length,
            slave=self.slave_id,
        )
        if response.isError():
            raise Exception(f"Modbus read_holding_registers error at {start}")
        return response.registers

    def _read_block(self, start: int, length: int):
        return self._read_input(start, length)

    def _group_contiguous(self, regs: list[dict]) -> list[list[dict]]:
        if not regs:
            return []

        ordered_regs = sorted(regs, key=lambda reg: reg["address"])
        groups = [[ordered_regs[0]]]

        for reg in ordered_regs[1:]:
            previous = groups[-1][-1]
            previous_end = previous["address"] + previous["length"]
            if reg["address"] == previous_end:
                groups[-1].append(reg)
            else:
                groups.append([reg])

        return groups

    def _read_group(self, regs: list[dict], read_kind: str = "input") -> Dict[str, Any]:
        if not regs:
            return {}

        result = {}
        reader = self._read_input if read_kind == "input" else self._read_holding

        for group in self._group_contiguous(regs):
            start = group[0]["address"]
            end = max(reg["address"] + reg["length"] - 1 for reg in group)
            raw = reader(start, end - start + 1)

            ordered = []
            for reg in group:
                idx = reg["address"] - start
                ordered.extend(raw[idx: idx + reg["length"]])

            result.update(self.parse(ordered, group))

        return result

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

        # Canadian Solar word order: Big Endian (High word first)
        if data_type == "uint32":
            if len(registers) < 2:
                return None
            high = registers[0]
            low = registers[1]
            return ((high & 0xFFFF) << 16) | (low & 0xFFFF)

        if data_type == "sint32":
            if len(registers) < 2:
                return None
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

    def parse(self, raw_block: Dict[str, Any], reg_list: list = None) -> Dict[str, Any]:
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
            parsed = self._read_group(self.register_map()["info"], read_kind="holding")
            rated_kw = parsed.get("rated_power", 110.0) or 110.0
            dsp_ver = str(parsed.get("dsp_version", "1.0"))
            arm_ver = str(parsed.get("arm_version", "1.0"))

            return {
                "brand": "CanadianSolar",
                "model": "CSI-110KTL-T400GL02-E",
                "serial_number": parsed.get("serial_number", ""),
                "capacity_kw": rated_kw,
                "mppt_count": 10,
                "firmware_version": f"ARM:{arm_ver} DSP:{dsp_ver}",
                "phase_count": 3,
                "strings_per_mppt": 2,
                "string_count": 20,
                "rate_dc_kwp": rated_kw,
                "rate_ac_kw": rated_kw,
                "is_active": True,
                "slave_id": self.slave_id,
                "usage_start_at": datetime.now().isoformat(),
                "usage_end_at": None,
                "replaced_by_id": None,
            }
        except Exception:
            return {
                "brand": "CanadianSolar",
                "model": "CSI-110KTL-T400GL02-E",
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
                "replaced_by_id": None,
            }

    def read_ac(self) -> Dict[str, Any]:
        return self._read_group(self.register_map()["ac"])

    def read_dc(self) -> Dict[str, Any]:
        return self._read_group(self.register_map()["dc"])

    def read_string(self) -> Dict[str, Any]:
        return self._read_group(self.register_map()["string"])

    def read_stat(self) -> Dict[str, Any]:
        regs = self.register_map().get("stat", [])
        return self._read_group(regs) if regs else {}

    def read_power(self) -> int:
        """AC inverter power in watts (input `p_inv_w`, address 0x8106)."""
        regs = self._read_input(0x8106, 1)
        value = self._convert(regs, "sint16")
        if value is None:
            raise Exception("read_power: invalid register data")
        return int(value * 100.0)

    # =========================================================
    # ================= FAULTS & STATES =======================
    # =========================================================

    def read_states_and_faults(self) -> Dict[str, Any]:
        state_id = 0
        try:
            res_state = self.transport.read_input_registers(
                address=0x8300,
                count=1,
                slave=self.slave_id,
            )
            if not res_state.isError():
                state_id = res_state.registers[0]
        except Exception:
            pass

        faults = [0] * 10
        try:
            res_fault = self.transport.read_input_registers(
                address=0x8400,
                count=10,
                slave=self.slave_id,
            )
            if not res_fault.isError() and len(res_fault.registers) >= 10:
                faults = res_fault.registers
        except Exception:
            pass

        return {
            "state_id": state_id,
            "fault_code": faults[0],      # Internal alarm
            "fault_code_1": faults[1],    # Internal recoverable fault 1
            "fault_code_2": faults[2],    # Internal recoverable fault 2
            "fault_code_3": faults[3],    # Internal recoverable fault 3
            "fault_code_4": faults[4],    # Internal recoverable fault 4
            "fault_code_5": faults[5],    # Internal recoverable fault 5
            "fault_code_6": faults[6],    # Internal recoverable fault 6
            "fault_code_7": faults[7],    # Internal recoverable fault 7
            "fault_permanent": faults[8], # Permanent internal failure
            "fault_armc": faults[9],      # ARMC fault
        }

    # =========================================================
    # ================= READ ALL ==============================
    # =========================================================

    def read_all(self) -> Dict[str, Any]:
        data = {}

        data.update(self.read_info())
        data.update(self.read_ac())

        dc = self.read_dc()
        strings = self.read_string()

        data.update(dc)
        data.update(strings)

        try:
            data.update(self.read_stat())
        except Exception:
            pass

        # Calculate MPPT currents
        for i in range(1, 11):
            s1 = strings.get(f"string_{2 * i - 1}_current")
            s2 = strings.get(f"string_{2 * i}_current")
            if s1 is not None and s2 is not None:
                data[f"mppt_{i}_current"] = round(s1 + s2, 2)

        try:
            data.update(self.read_states_and_faults())
        except Exception:
            pass

        return data

    # =========================================================
    # ================= CONTROL ===============================
    # =========================================================

    @staticmethod
    def _ensure_write_ok(response, action: str) -> bool:
        if response is None:
            raise Exception(f"{action} returned no response")
        if hasattr(response, "isError") and response.isError():
            raise Exception(f"{action} failed: {response}")
        return True

    def enable_power_limit(self, enable: bool) -> bool:
        # Ghi vào 0x0602: 1 (Remote derating) / 0 (No adjustment)
        val = 1 if enable else 0
        response = self.transport.write_register(
            address=0x0602,
            value=val,
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Enable power limit={enable}")

    def write_power_limit_percent(self, percent: float) -> bool:
        # Bật chế độ remote derating (0x0602 = 1)
        self.enable_power_limit(True)

        # 0x0708: Remote active power setting, Ratio 0.1 % (e.g. 100% -> 1000)
        val = int(percent * 10)
        response = self.transport.write_register(
            address=0x0708,
            value=val,
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Write power limit percent {percent}%")

    def write_power_limit_kw(self, kw: float) -> bool:
        # Bật chế độ local derating (0x0602 = 2)
        response_mode = self.transport.write_register(
            address=0x0602,
            value=2,
            slave=self.slave_id,
        )
        self._ensure_write_ok(response_mode, "Set active power mode to Local derating (0x0602=2)")

        # 0x0524: Active power deloading fixed value, Ratio 0.1 kW (e.g. 110 kW -> 1100)
        val = int(kw * 10)
        response = self.transport.write_register(
            address=0x0524,
            value=val,
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Write power limit kW {kw}kW")

    def set_power_percent(self, percent: float) -> bool:
        return self.write_power_limit_percent(percent)

    def set_power_kw(self, kw: float) -> bool:
        return self.write_power_limit_kw(kw)

    def set_power_w(self, watt: float) -> bool:
        return self.set_power_kw(watt / 1000.0)

    def read_power_limit(self) -> Dict[str, Any]:
        res_mode = self.transport.read_holding_registers(
            address=0x0602,
            count=1,
            slave=self.slave_id,
        )
        if res_mode.isError():
            raise Exception(f"Read power limit mode failed: {res_mode}")

        mode = res_mode.registers[0]
        limit_w = 0.0

        if mode == 1:
            res_val = self.transport.read_holding_registers(
                address=0x0708,
                count=1,
                slave=self.slave_id,
            )
            if not res_val.isError():
                val_0_1_percent = res_val.registers[0]
                limit_percent = val_0_1_percent / 10.0
                info = self.read_info()
                capacity_kw = info.get("capacity_kw", 110.0)
                limit_w = (limit_percent / 100.0) * capacity_kw * 1000.0
        elif mode == 2:
            res_val = self.transport.read_holding_registers(
                address=0x0524,
                count=1,
                slave=self.slave_id,
            )
            if not res_val.isError():
                val_0_1_kw = res_val.registers[0]
                if val_0_1_kw & 0x8000:
                    val_0_1_kw -= 0x10000
                limit_w = (val_0_1_kw / 10.0) * 1000.0
        else:
            info = self.read_info()
            limit_w = info.get("capacity_kw", 110.0) * 1000.0

        return {
            "mode": mode,
            "limit_w": limit_w,
        }

    def read_power_limit_percent(self) -> float:
        try:
            res_mode = self.transport.read_holding_registers(
                address=0x0602,
                count=1,
                slave=self.slave_id,
            )
            if res_mode.isError() or not res_mode.registers:
                return 100.0
            mode = res_mode.registers[0]
            if mode == 1:
                res_val = self.transport.read_holding_registers(
                    address=0x0708,
                    count=1,
                    slave=self.slave_id,
                )
                if not res_val.isError() and res_val.registers:
                    return float(res_val.registers[0]) / 10.0
            elif mode == 2:
                res_val = self.transport.read_holding_registers(
                    address=0x0524,
                    count=1,
                    slave=self.slave_id,
                )
                if not res_val.isError() and res_val.registers:
                    val_0_1_kw = res_val.registers[0]
                    if val_0_1_kw & 0x8000:
                        val_0_1_kw -= 0x10000
                    kw = val_0_1_kw / 10.0
                    info = self.read_info()
                    capacity_kw = info.get("capacity_kw", 110.0) or 110.0
                    return (kw / capacity_kw) * 100.0
            return 100.0
        except Exception:
            return 100.0
