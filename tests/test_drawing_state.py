import threading
from unittest.mock import patch

from spire_painter.drawing_state import DrawingState


def _make_state():
    """Create a fresh DrawingState without triggering module-level hotkeys."""
    return DrawingState()


class TestDrawingState:
    def test_initial_state(self):
        s = _make_state()
        assert s.abort is False
        assert s.pause is False
        assert s.drawing is False

    def test_trigger_pause(self):
        s = _make_state()
        with patch("spire_painter.drawing_state.left_click_up"), \
             patch("spire_painter.drawing_state.right_click_up"):
            s.trigger_pause()
        assert s.pause is True
        assert s.abort is False

    def test_trigger_resume(self):
        s = _make_state()
        with patch("spire_painter.drawing_state.left_click_up"), \
             patch("spire_painter.drawing_state.right_click_up"):
            s.trigger_pause()
            s.trigger_resume()
        assert s.pause is False

    def test_trigger_abort(self):
        s = _make_state()
        with patch("spire_painter.drawing_state.left_click_up"), \
             patch("spire_painter.drawing_state.right_click_up"):
            s.trigger_abort()
        assert s.abort is True
        assert s.pause is False

    def test_abort_clears_pause(self):
        s = _make_state()
        with patch("spire_painter.drawing_state.left_click_up"), \
             patch("spire_painter.drawing_state.right_click_up"):
            s.trigger_pause()
            assert s.pause is True
            s.trigger_abort()
            assert s.pause is False

    def test_reset(self):
        s = _make_state()
        with patch("spire_painter.drawing_state.left_click_up"), \
             patch("spire_painter.drawing_state.right_click_up"):
            s.trigger_abort()
        s.reset()
        assert s.abort is False
        assert s.pause is False

    def test_pause_ignored_when_already_paused(self):
        s = _make_state()
        with patch("spire_painter.drawing_state.left_click_up"), \
             patch("spire_painter.drawing_state.right_click_up"):
            s.trigger_pause()
            s.trigger_pause()  # should not crash or change state
        assert s.pause is True

    def test_pause_ignored_when_aborted(self):
        s = _make_state()
        with patch("spire_painter.drawing_state.left_click_up"), \
             patch("spire_painter.drawing_state.right_click_up"):
            s.trigger_abort()
            s.trigger_pause()  # should be ignored
        assert s.pause is False
        assert s.abort is True

    def test_thread_safety(self):
        """Multiple threads setting state concurrently shouldn't crash."""
        s = _make_state()
        errors = []

        def toggle_pause():
            try:
                for _ in range(100):
                    with patch("spire_painter.drawing_state.left_click_up"), \
                         patch("spire_painter.drawing_state.right_click_up"):
                        s.trigger_pause()
                        s.trigger_resume()
            except Exception as e:
                errors.append(e)

        def toggle_abort():
            try:
                for _ in range(100):
                    with patch("spire_painter.drawing_state.left_click_up"), \
                         patch("spire_painter.drawing_state.right_click_up"):
                        s.trigger_abort()
                        s.reset()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle_pause) for _ in range(3)]
        threads += [threading.Thread(target=toggle_abort) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
