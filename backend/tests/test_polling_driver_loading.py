import unittest
from unittest.mock import MagicMock
from backend.services.polling_service import PollingService
from backend.drivers.inverters.solis_S6_EH3P99_9K10_NV_YD_H import SolisS6HybridDriver
from backend.drivers.inverters.solis_110k import Solis110k
from backend.drivers.inverters.solis_100k import Solis100k
from backend.drivers.inverters.sungrow_sg110cx import Sungrowsg110cx
from backend.drivers.inverters.huawei_sun2000_110ktl import Huaweisun2000110ktl

class TestPollingDriverLoading(unittest.TestCase):
    def setUp(self):
        self.project_svc = MagicMock()
        self.cache_db = MagicMock()
        self.realtime_db = MagicMock()
        self.polling_svc = PollingService(self.project_svc, self.cache_db, self.realtime_db)
        self.transport = MagicMock()

    def test_get_driver_solis_s6_hybrid_with_dots(self):
        """Kiểm tra model chứa dấu chấm: S6-EH3P99.9K10-NV-YD-H"""
        driver = self.polling_svc._get_driver("Solis", self.transport, slave_id=1, model="S6-EH3P99.9K10-NV-YD-H")
        self.assertIsNotNone(driver)
        self.assertIsInstance(driver, SolisS6HybridDriver)

    def test_get_driver_solis_s6_hybrid_lowercase(self):
        """Kiểm tra tên model viết thường hoặc biến thể: s6_eh3p99.9k10_nv_yd_h"""
        driver = self.polling_svc._get_driver("solis", self.transport, slave_id=1, model="s6_eh3p99.9k10_nv_yd_h")
        self.assertIsNotNone(driver)
        self.assertIsInstance(driver, SolisS6HybridDriver)

    def test_get_driver_solis_110k(self):
        """Kiểm tra model Solis 110K"""
        driver = self.polling_svc._get_driver("Solis", self.transport, slave_id=1, model="110K")
        self.assertIsNotNone(driver)
        self.assertIsInstance(driver, Solis110k)

    def test_get_driver_solis_100k(self):
        """Kiểm tra model Solis 100K"""
        driver = self.polling_svc._get_driver("Solis", self.transport, slave_id=1, model="100K")
        self.assertIsNotNone(driver)
        self.assertIsInstance(driver, Solis100k)

    def test_get_driver_sungrow_sg110cx(self):
        """Kiểm tra model Sungrow SG110CX"""
        driver = self.polling_svc._get_driver("Sungrow", self.transport, slave_id=1, model="SG110CX")
        self.assertIsNotNone(driver)
        self.assertIsInstance(driver, Sungrowsg110cx)

    def test_get_driver_huawei_sun2000_110ktl(self):
        """Kiểm tra model Huawei SUN2000-110KTL"""
        driver = self.polling_svc._get_driver("Huawei", self.transport, slave_id=1, model="SUN2000-110KTL")
        self.assertIsNotNone(driver)
        self.assertIsInstance(driver, Huaweisun2000110ktl)

if __name__ == "__main__":
    unittest.main()
