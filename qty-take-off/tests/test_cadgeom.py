"""Pure CAD geometry tests (no ezdxf dependency)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import cadgeom as geometry


def total(segments):
    return sum(geometry.seg_len(start, end) for start, end in segments)


class MergeCollinear(unittest.TestCase):
    def test_exact_duplicate_counted_once(self):
        line = ((0, 0), (10, 0))
        self.assertAlmostEqual(total(geometry.merge_collinear([line, line])), 10)

    def test_partial_overlap_counted_once(self):
        segments = [((0, 0), (6, 0)), ((4, 0), (10, 0))]
        self.assertAlmostEqual(total(geometry.merge_collinear(segments)), 10)

    def test_reversed_and_contained_overlap_counted_once(self):
        segments = [((0, 0), (10, 0)), ((8, 0), (2, 0))]
        self.assertAlmostEqual(total(geometry.merge_collinear(segments)), 10)

    def test_touching_segments_merge(self):
        segments = [((0, 0), (5, 0)), ((5, 0), (10, 0))]
        self.assertAlmostEqual(total(geometry.merge_collinear(segments)), 10)

    def test_gap_is_not_filled(self):
        segments = [((0, 0), (4, 0)), ((6, 0), (10, 0))]
        self.assertAlmostEqual(total(geometry.merge_collinear(segments)), 8)

    def test_parallel_lines_outside_tolerance_remain_separate(self):
        segments = [((0, 0), (10, 0)), ((0, 0.7), (10, 0.7))]
        self.assertAlmostEqual(total(geometry.merge_collinear(segments)), 20)

    def test_small_offset_within_tolerance_merges(self):
        segments = [((0, 0), (10, 0)), ((0, 0.001), (10, 0.001))]
        self.assertAlmostEqual(total(geometry.merge_collinear(segments)), 10)

    def test_3d_and_diagonal_segments(self):
        diagonal = [((0, 0, 0), (3, 4, 0)), ((3, 4, 0), (0, 0, 0))]
        vertical = [((0, 0, 0), (0, 0, 2.5)), ((0, 0, 1), (0, 0, 4))]
        self.assertAlmostEqual(total(geometry.merge_collinear(diagonal)), 5)
        self.assertAlmostEqual(total(geometry.merge_collinear(vertical)), 4)

    def test_zero_length_segment_is_ignored(self):
        self.assertEqual(geometry.merge_collinear([((1, 1), (1, 1))]), [])


class OrientationAndRuns(unittest.TestCase):
    def test_orientation_split(self):
        segments = [
            ((0, 0, 0), (10, 0, 0)),
            ((0, 0, 0), (0, 0, 2.5)),
            ((0, 0, 0), (3, 0, 4)),
        ]
        orientation = geometry.orient_split(segments)
        self.assertEqual(orientation, {"h": 10, "v": 2.5, "d": 5})

    def test_connected_segments_form_run_and_bbox(self):
        segments = [((0, 0), (5, 0)), ((5, 0), (5, 3)), ((20, 20), (30, 20))]
        runs = geometry.cluster_runs(segments)
        self.assertEqual([run["n"] for run in runs], [1, 2])
        self.assertAlmostEqual(runs[0]["length_m"], 10)
        self.assertAlmostEqual(runs[1]["length_m"], 8)
        self.assertEqual(runs[1]["bbox"], [0, 0, 5, 3])
        self.assertAlmostEqual(runs[1]["h_m"], 8)
        self.assertEqual(runs[1]["v_m"], 0)


if __name__ == "__main__":
    unittest.main()
