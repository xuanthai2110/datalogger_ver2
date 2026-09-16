# backend/drivers/batteries/base_battery_driver.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseBatteryDriver(ABC):
    """
    Abstract base class cho tất cả Battery BMS Drivers.
    Các hãng Pin (Pylontech, Seplos, Pace, Deye, BYD,...) kết nối qua BMS sẽ kế thừa class này.
    """

    @abstractmethod
    def __init__(self, transport, slave_id: int = 1):
        self.transport = transport
        self.slave_id = slave_id

    @abstractmethod
    def read_info(self) -> Optional[Dict[str, Any]]:
        """
        Đọc thông tin cố định từ BMS Pin (Serial Number gốc phần cứng, Hãng, Model, Dung lượng...).
        Trả về dict nếu thành công, trả về None nếu không đọc được hoặc không có phản hồi.
        """
        pass

    @abstractmethod
    def read_telemetry(self) -> Optional[Dict[str, Any]]:
        """
        Đọc các thông số vận hành thời gian thực (V, I, P, SOC, SOH, Nhiệt độ cell, Điện áp cell).
        """
        pass
