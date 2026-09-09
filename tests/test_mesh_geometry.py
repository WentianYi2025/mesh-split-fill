"""Small geometric invariants; run with Python's unittest discovery."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mesh_geometry import GeometryError, make_complementary_patch, partition_triangles


VERTICES = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0],
            [2.0, 2.0, 0.0], [0.0, 2.0, 0.0], [1.0, 1.0, 0.6]]
TRIANGLES = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]


def normal(vertices, triangle):
    p, q, r = (vertices[i] for i in triangle)
    u = [q[k] - p[k] for k in range(3)]
    v = [r[k] - p[k] for k in range(3)]
    return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0]]


class PartitionTests(unittest.TestCase):
    def test_provenance_reconstructs_every_source_face_without_motion(self):
        points, faces = copy.deepcopy(VERTICES), copy.deepcopy(TRIANGLES)
        result = partition_triangles(points, faces, ["a", "b", "b", "a"],
                                     part_ids=["b", "a"])
        self.assertEqual([p["part_id"] for p in result["parts"]], ["b", "a"])
        reconstructed = {}
        for part in result["parts"]:
            for local, source in enumerate(part["source_vertex_indices"]):
                self.assertEqual(part["vertices"][local], points[source])
            for local, source in enumerate(part["source_face_indices"]):
                reconstructed[source] = [part["source_vertex_indices"][i]
                                         for i in part["triangles"][local]]
        self.assertEqual(reconstructed, dict(enumerate(TRIANGLES)))
        self.assertEqual(sum(len(p["triangles"]) for p in result["parts"]), len(faces))
        self.assertEqual(points, VERTICES)
        self.assertEqual(faces, TRIANGLES)
        result["parts"][0]["vertices"][0][0] = 100
        self.assertEqual(points, VERTICES)

    def test_invalid_or_incomplete_labels_are_rejected(self):
        for labels, ids in [([0], None), ([0, 0, 1, -1], None),
                            ([0, 0, 1, None], None), ([0, 0, 1, True], None),
                            ([0, 0, 1, 1], [0]), ([0, 0, 1, 1], [0, 1, 2]),
                            ([0, 0, 1, 1], [0, 0, 1])]:
            with self.subTest(labels=labels, ids=ids), self.assertRaises(GeometryError):
                partition_triangles(VERTICES, TRIANGLES, labels, part_ids=ids)

    def test_equal_positions_do_not_merge_distinct_source_indices(self):
        points = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]]
        result = partition_triangles(points, [[0, 1, 2], [3, 2, 1]], [0, 0])
        self.assertEqual(result["parts"][0]["source_vertex_indices"], [0, 1, 2, 3])


class ComplementTests(unittest.TestCase):
    def test_pair_has_equal_positions_and_opposite_normals(self):
        original = copy.deepcopy(VERTICES)
        result = make_complementary_patch(VERTICES, TRIANGLES, [0, 1, 2, 3])
        a, b = result["forward"], result["reverse"]
        self.assertEqual(a["vertices"], b["vertices"])
        self.assertEqual(result["vertex_pairs"], [[i, i] for i in range(5)])
        for fa, fb in zip(a["triangles"], b["triangles"]):
            self.assertEqual(normal(a["vertices"], fa),
                             [-n for n in normal(b["vertices"], fb)])
        self.assertFalse(result["checks"]["self_intersection_tested"])
        self.assertEqual(result["clearance"], 0.0)
        b["vertices"][0][0] = 99
        self.assertEqual(a["vertices"], original)
        self.assertEqual(VERTICES, original)

    def test_wrong_boundary_and_inconsistent_winding_are_rejected(self):
        for loop in ([0, 3, 2, 1], [0, 1, 2], [0, 1, 2, 3, 0]):
            with self.subTest(loop=loop), self.assertRaises(GeometryError):
                make_complementary_patch(VERTICES, TRIANGLES, loop)
        faces = copy.deepcopy(TRIANGLES)
        faces[0].reverse()
        with self.assertRaises(GeometryError):
            make_complementary_patch(VERTICES, faces, [0, 1, 2, 3])

    def test_unused_vertices_and_multiple_components_are_rejected(self):
        with self.assertRaises(GeometryError):
            make_complementary_patch(VERTICES + [[8, 8, 8]], TRIANGLES, [0, 1, 2, 3])
        points = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [3, 0, 0], [4, 0, 0], [3, 1, 0]]
        with self.assertRaises(GeometryError):
            make_complementary_patch(points, [[0, 1, 2], [3, 4, 5]], [0, 1, 2])


class InputGuards(unittest.TestCase):
    def test_degenerate_duplicate_and_invalid_triangles_are_rejected(self):
        cases = [([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 1, 2]]),
                 (VERTICES, [[0, 0, 1]]), (VERTICES, [[0, 1, 99]]),
                 (VERTICES, [[0, 1, 4], [4, 1, 0]]),
                 ([[float("nan"), 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])]
        for points, faces in cases:
            with self.subTest(faces=faces), self.assertRaises(GeometryError):
                partition_triangles(points, faces, [0] * len(faces))
            with self.subTest(patch=faces), self.assertRaises(GeometryError):
                make_complementary_patch(points, faces, [0, 1, 2])

    def test_relative_tolerance_behaves_consistently_across_model_scales(self):
        for scale in (1e-8, 1.0, 1e8):
            points = [[scale * x for x in p] for p in VERTICES]
            result = make_complementary_patch(points, TRIANGLES, [0, 1, 2, 3])
            self.assertTrue(result["checks"]["nondegenerate_triangles"])
            skinny = [[0, 0, 0], [scale, 0, 0], [scale, scale * 1e-14, 0]]
            with self.assertRaises(GeometryError):
                partition_triangles(skinny, [[0, 1, 2]], [0])


if __name__ == "__main__":
    unittest.main()
