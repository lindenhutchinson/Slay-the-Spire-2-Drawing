import math

from spire_painter.drawing_engine import (
    _cos_between, _dist_sq, _to_screen, _order_and_merge_strokes,
)


class TestCosBetween:
    def test_same_direction(self):
        cos = _cos_between(1, 0, 1, 0)
        assert cos > 0.99

    def test_opposite_direction(self):
        cos = _cos_between(1, 0, -1, 0)
        assert cos < -0.99

    def test_perpendicular(self):
        cos = _cos_between(1, 0, 0, 1)
        assert abs(cos) < 0.01

    def test_45_degrees(self):
        cos = _cos_between(1, 0, 1, 1)
        expected = math.cos(math.radians(45))
        assert abs(cos - expected) < 0.01

    def test_zero_vector_returns_1(self):
        cos = _cos_between(0, 0, 1, 0)
        assert cos == 1.0

    def test_both_zero(self):
        cos = _cos_between(0, 0, 0, 0)
        assert cos == 1.0


class TestDistSq:
    def test_same_point(self):
        assert _dist_sq((5, 5), (5, 5)) == 0

    def test_horizontal(self):
        assert _dist_sq((0, 0), (3, 0)) == 9

    def test_diagonal(self):
        assert _dist_sq((0, 0), (3, 4)) == 25


class TestToScreen:
    def test_basic_conversion(self):
        point = [[10, 20]]  # OpenCV contour point format
        x, y = _to_screen(point, 100, 200, 2.0)
        assert x == 120
        assert y == 240

    def test_offset(self):
        point = [[0, 0]]
        x, y = _to_screen(point, 50, 60, 1.0)
        assert x == 50
        assert y == 60

    def test_scale(self):
        point = [[10, 10]]
        x, y = _to_screen(point, 0, 0, 0.5)
        assert x == 5
        assert y == 5


class TestOrderAndMergeStrokes:
    def test_empty_input(self):
        assert _order_and_merge_strokes([], 10) == []

    def test_single_stroke(self):
        strokes = [[(0, 0), (10, 10)]]
        result = _order_and_merge_strokes(strokes, 10)
        assert len(result) == 1
        assert result[0] == [(0, 0), (10, 10)]

    def test_nearest_neighbor_ordering(self):
        """Strokes should be reordered so the pen travels less."""
        strokes = [
            [(100, 100), (110, 100)],  # far from origin
            [(0, 0), (10, 0)],          # close to origin
            [(12, 0), (20, 0)],         # close to second stroke
        ]
        result = _order_and_merge_strokes(strokes, 0)
        # Should start with the stroke nearest origin
        assert result[0][0] == (0, 0) or result[0][-1] == (0, 0)

    def test_merge_close_strokes(self):
        """Strokes with endpoints within merge threshold should merge into one group."""
        strokes = [
            [(0, 0), (10, 0)],
            [(12, 0), (20, 0)],  # gap of 2px, within threshold of 5
        ]
        result = _order_and_merge_strokes(strokes, 5)
        assert len(result) == 1
        # 4 real points + 1 None sentinel at the merge boundary
        assert len(result[0]) == 5
        assert None in result[0]

    def test_no_merge_far_strokes(self):
        """Strokes far apart should remain separate."""
        strokes = [
            [(0, 0), (10, 0)],
            [(100, 100), (110, 100)],  # far away
        ]
        result = _order_and_merge_strokes(strokes, 5)
        assert len(result) == 2

    def test_direction_optimization(self):
        """Should reverse a stroke if its end is closer than its start."""
        strokes = [
            [(0, 0), (10, 0)],
            [(20, 0), (11, 0)],  # end (11,0) is closer to (10,0) than start (20,0)
        ]
        result = _order_and_merge_strokes(strokes, 5)
        # Second stroke should be reversed so it starts at (11,0) near (10,0)
        # and merged since gap is 1px < 5px threshold
        assert len(result) == 1
