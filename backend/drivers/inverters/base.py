# drivers/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseDriver(ABC):
    """
    Abstract base class cho tất cả inverter drivers.

    Mỗi hãng inverter phải implement đầy đủ các method dưới đây.
    """

    # =========================================================
    # ===================== INIT ===============================
    # =========================================================

    @abstractmethod
    def __init__(self, transport, slave_id: int): #Khởi tạo driver với transport (Modbus RTU/TCP) và slave ID của inverter.
        pass

    #============khai báo registor của inverter================================

    @abstractmethod
    def register_map(self) -> Dict[str, Any]: #Trả về một dict chứa thông tin về các register của inverter, bao gồm địa chỉ, kiểu dữ liệu, v.v.
        pass

    #================ hàm parse dữ liệu từ raw register sang engineering value =========================
    @abstractmethod
    def parse(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    # =============Các hàm đọc dữ liệu từ inverter =========================
    @abstractmethod
    def read_ac(self) -> Dict[str, Any]: #Đọc toàn bộ AC data:
        pass

    @abstractmethod
    def read_dc(self) -> Dict[str, Any]: #Đọc toàn bộ DC data:
        pass

    @abstractmethod
    def read_info(self) -> Dict[str, Any]: #Đọc thông tin inverter như model, firmware version, serial number, v.v.
        pass

    @abstractmethod
    def read_string(self) -> Dict[str, Any]: #Đọc dữ liệu từng string :
        pass

    @abstractmethod
    def read_all(self) -> Dict[str, Any]: #Đọc tất cả dữ liệu (AC, DC, info, string) trong một lần gọi.
        pass

    #================ Điều khiển inverter =========================

    @abstractmethod
    def enable_power_limit(self, enable: bool) -> bool: #Bật / tắt chế độ power limit.
        pass

    @abstractmethod
    def write_power_limit_kw(self, kw: float) -> bool: #Ghi giá trị giới hạn công suất (kW).
        pass
    @abstractmethod
    def read_states_and_faults(self) -> Dict[str, Any]: #Đọc trạng thái và lỗi của inverter.
        pass

    @abstractmethod
    def write_power_limit_percent(self, percent: float) -> bool: #Ghi giá trị giới hạn công suất (%).
        pass

    @abstractmethod
    def read_power_limit_percent(self) -> float: #Đọc lại giới hạn công suất (%).
        pass

        