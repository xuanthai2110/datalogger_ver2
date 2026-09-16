import os
import sys
import tempfile
import threading
import time
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.db_manager import CacheDB, RealtimeDB


class TestMultithreadedDB(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db_path = os.path.join(self.temp_dir.name, "cache.db")
        self.realtime_db_path = os.path.join(self.temp_dir.name, "realtime.db")
        self.cache_db = CacheDB(self.cache_db_path)
        self.realtime_db = RealtimeDB(self.realtime_db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_concurrent_cache_db_access(self):
        """Kiểm tra 10 thread đồng thời đọc và ghi vào CacheDB mà không gặp lỗi database is locked."""
        errors = []

        def worker_writer(thread_id):
            try:
                for i in range(50):
                    self.cache_db.upsert_inverter_ac(
                        inverter_id=thread_id,
                        project_id=1,
                        data={
                            "ir": 100.0 + i,
                            "temp_c": 45.0,
                            "p_inv_w": 50000.0,
                            "q_inv_var": 0.0,
                            "v_a": 230.0,
                            "v_b": 230.0,
                            "v_c": 230.0,
                            "i_a": 72.0,
                            "i_b": 72.0,
                            "i_c": 72.0,
                            "pf": 1.0,
                            "grid_hz": 50.0,
                            "e_daily": 150.0,
                            "e_total": 50000.0,
                        },
                    )
                    self.cache_db.update_mppt_max(thread_id, 1, 600.0, 15.0, 9000.0)
                    self.cache_db.update_string_max(thread_id, 1, 15.0)
                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, e))

        def worker_reader(thread_id):
            try:
                for i in range(50):
                    _ = self.cache_db.get_ac_cache(thread_id % 5 + 1)
                    _ = self.cache_db.get_all_ac_cache()
                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, e))

        threads = []
        for tid in range(1, 6):
            t_w = threading.Thread(target=worker_writer, args=(tid,))
            t_r = threading.Thread(target=worker_reader, args=(tid,))
            threads.extend([t_w, t_r])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent CacheDB errors: {errors}")

    def test_concurrent_realtime_db_access(self):
        """Kiểm tra 10 thread đồng thời đọc và ghi vào RealtimeDB mà không gặp lỗi database is locked."""
        errors = []

        def worker_writer(thread_id):
            try:
                for i in range(30):
                    self.realtime_db.post_to_outbox(
                        project_id=1,
                        server_id=17,
                        data={"type": "telemetry", "seq": i},
                    )
                    self.realtime_db.push_evn_command(1, "P", "PERCENT", 90.0)
                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, e))

        def worker_reader(thread_id):
            try:
                for _ in range(30):
                    _ = self.realtime_db.get_all_outbox()
                    _ = self.realtime_db.get_pending_evn_commands()
                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, e))

        threads = []
        for tid in range(1, 6):
            t_w = threading.Thread(target=worker_writer, args=(tid,))
            t_r = threading.Thread(target=worker_reader, args=(tid,))
            threads.extend([t_w, t_r])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent RealtimeDB errors: {errors}")


if __name__ == "__main__":
    unittest.main()
