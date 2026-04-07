from spire_painter.mouse import _v_left, _v_top, _v_width, _v_height, refresh_metrics, precise_sleep
import time


class TestMouseMetrics:
    def test_metrics_initialized(self):
        """Cached metrics should be populated on import."""
        assert _v_width > 0
        assert _v_height > 0

    def test_refresh_metrics_doesnt_crash(self):
        refresh_metrics()
        from spire_painter.mouse import _v_width, _v_height
        assert _v_width > 0
        assert _v_height > 0


class TestPreciseSleep:
    def test_short_sleep_is_faster_than_default(self):
        """precise_sleep(0.001) should complete in well under 20ms."""
        start = time.perf_counter()
        precise_sleep(0.001)
        elapsed = time.perf_counter() - start
        # Should be under 5ms (default time.sleep would be ~15ms)
        assert elapsed < 0.005

    def test_zero_sleep(self):
        precise_sleep(0)  # should not crash

    def test_negative_sleep(self):
        precise_sleep(-1)  # should not crash
