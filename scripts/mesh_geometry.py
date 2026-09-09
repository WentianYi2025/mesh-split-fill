"""Small, dependency-free mesh operations with explicit geometry inputs.

These functions do not infer semantic labels, smooth a cut, fill an arbitrary
hole, weld a shell, test self-intersections, or create manufacturing clearance.
All returned indices are zero-based. Input arrays are never mutated.
"""

from collections import defaultdict
from math import hypot, isfinite
from numbers import Integral, Real


class GeometryError(ValueError):
    """The supplied mesh does not satisfy an operation's preconditions."""


def _length_tolerance(vertices, relative_tolerance, absolute_tolerance):
    for name, value in (("relative_tolerance", relative_tolerance),
                        ("absolute_tolerance", absolute_tolerance)):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise GeometryError(f"{name} must be a finite nonnegative number")
        if not isfinite(value) or value < 0:
            raise GeometryError(f"{name} must be a finite nonnegative number")
    spans = [max(p[k] for p in vertices) - min(p[k] for p in vertices)
             for k in range(3)]
    scale = hypot(*spans)
    tolerance = max(absolute_tolerance, relative_tolerance * scale)
    if not isfinite(scale) or not isfinite(tolerance) or scale <= 0:
        raise GeometryError("Mesh extent must be finite and positive")
    return float(tolerance)


def _validated_mesh(vertices, triangles, relative_tolerance, absolute_tolerance):
    try:
        points = [tuple(p) for p in vertices]
        faces = [tuple(f) for f in triangles]
    except TypeError as exc:
        raise GeometryError("Vertices and triangles must be sequences of rows") from exc
    if not points or not faces:
        raise GeometryError("A nonempty triangle mesh is required")
    for i, p in enumerate(points):
        if len(p) != 3 or any(isinstance(x, bool) or not isinstance(x, Real)
                              or not isfinite(x) for x in p):
            raise GeometryError(f"Vertex {i} must have three finite real coordinates")
    tolerance = _length_tolerance(points, relative_tolerance, absolute_tolerance)
    seen = set()
    for i, f in enumerate(faces):
        if len(f) != 3 or any(isinstance(x, bool) or not isinstance(x, Integral)
                              or x < 0 or x >= len(points) for x in f):
            raise GeometryError(f"Triangle {i} must have three valid vertex indices")
        if len(set(f)) != 3:
            raise GeometryError(f"Triangle {i} repeats a vertex")
        key = tuple(sorted(f))
        if key in seen:
            raise GeometryError(f"Triangle {i} duplicates another triangle")
        seen.add(key)
        p, q, r = (points[j] for j in f)
        u = tuple(q[k] - p[k] for k in range(3))
        v = tuple(r[k] - p[k] for k in range(3))
        w = tuple(r[k] - q[k] for k in range(3))
        longest = max(hypot(*u), hypot(*v), hypot(*w))
        if not isfinite(longest) or longest == 0:
            raise GeometryError(f"Triangle {i} has an invalid edge length")
        # Normalize before cross products, avoiding unnecessary area overflow.
        a = tuple(x / longest for x in u)
        b = tuple(x / longest for x in v)
        cross = (a[1] * b[2] - a[2] * b[1],
                 a[2] * b[0] - a[0] * b[2],
                 a[0] * b[1] - a[1] * b[0])
        altitude = hypot(*cross) * longest
        if not isfinite(altitude) or altitude <= tolerance:
            raise GeometryError(f"Triangle {i} is degenerate at length tolerance {tolerance:g}")
    return points, faces, tolerance


def _part_id(value):
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, Integral) and not isinstance(value, bool) and value >= 0:
        return int(value)
    raise GeometryError("Part labels must be nonempty strings or nonnegative integers")


def partition_triangles(vertices, triangles, labels, *, part_ids=None,
                        relative_tolerance=1e-12, absolute_tolerance=0.0):
    """Assign every source triangle to exactly one explicit part label.

    ``labels`` has one entry per triangle. Optional ``part_ids`` is the complete
    ordered part inventory: unknown labels, duplicate IDs, and empty declared
    parts are errors. Without it, order follows first appearance in labels.
    Existing face edges are used; no new seam, cap, or vertex is generated.

    Each returned part has vertices, triangles, source_vertex_indices, and
    source_face_indices. Coordinates and winding are copied without changes.
    Different source vertex IDs are never merged, even at equal coordinates.
    Local source indices refer to this supplied mesh, not to a prior pipeline.
    A part may be open or disconnected; inspect it before subsequent filling.
    UVs, corner normals, materials, and other attributes must be copied by the
    caller using the returned provenance; this function returns geometry only.

    Degeneracy uses minimum triangle altitude <= max(absolute_tolerance,
    relative_tolerance * source bounding-box diagonal), in input length units.
    This is an input guard, not an exported-float32 or self-intersection audit.
    """
    points, faces, tolerance = _validated_mesh(
        vertices, triangles, relative_tolerance, absolute_tolerance)
    try:
        owners = [_part_id(value) for value in labels]
    except TypeError as exc:
        raise GeometryError("Labels must be a sequence") from exc
    if len(owners) != len(faces):
        raise GeometryError("Exactly one label is required for every source triangle")
    if part_ids is None:
        order = list(dict.fromkeys(owners))
    else:
        try:
            order = [_part_id(value) for value in part_ids]
        except TypeError as exc:
            raise GeometryError("part_ids must be a sequence") from exc
        if len(set(order)) != len(order):
            raise GeometryError("Declared part IDs must be unique")
        if set(order) != set(owners):
            raise GeometryError("Declared parts must match all labels, with no empty or unknown parts")
    grouped = {label: [] for label in order}
    for face_id, label in enumerate(owners):
        grouped[label].append(face_id)
    parts = []
    for label in order:
        face_ids = grouped[label]
        source_ids = sorted({v for face_id in face_ids for v in faces[face_id]})
        remap = {source_id: local_id for local_id, source_id in enumerate(source_ids)}
        parts.append({"part_id": label,
                      "vertices": [list(points[i]) for i in source_ids],
                      "triangles": [[remap[v] for v in faces[i]] for i in face_ids],
                      "source_vertex_indices": source_ids,
                      "source_face_indices": face_ids})
    return {"parts": parts, "source_vertex_count": len(points),
            "source_face_count": len(faces), "length_tolerance": tolerance}


def make_complementary_patch(vertices, triangles, boundary_loop, *,
                             relative_tolerance=1e-12, absolute_tolerance=0.0):
    """Copy one explicitly supplied disk patch into two opposite windings.

    ``boundary_loop`` lists each boundary vertex once, with no repeated closing
    vertex, and follows the directed boundary of ``triangles``. The patch must
    use every supplied vertex and form one consistently oriented topological
    disk with manifold vertex fans. The reverse patch uses the SAME positions
    and connectivity with reversed winding; it is not a spatial reflection.

    This checks topology and triangle degeneracy, NOT embedded self-intersection,
    shell collisions, tangent continuity, intended bulge direction, or assembly
    fit. A folded or self-intersecting disk can pass these limited checks. The
    caller must perform those audits and stitch by explicit rim correspondence.
    Zero clearance is intentional; manufacturing clearance is separate work.
    """
    points, faces, tolerance = _validated_mesh(
        vertices, triangles, relative_tolerance, absolute_tolerance)
    try:
        loop = list(boundary_loop)
    except TypeError as exc:
        raise GeometryError("boundary_loop must be an ordered sequence") from exc
    if len(loop) < 3 or any(isinstance(v, bool) or not isinstance(v, Integral)
                            or v < 0 or v >= len(points) for v in loop):
        raise GeometryError("Boundary must contain at least three valid vertex indices")
    if len(set(loop)) != len(loop):
        raise GeometryError("Boundary vertices must be unique; omit the repeated closing vertex")
    used = {v for f in faces for v in f}
    if used != set(range(len(points))):
        raise GeometryError("A patch must not contain unused vertices")
    edges = defaultdict(list)
    incident = defaultdict(set)
    neighbors = defaultdict(set)
    for face_id, f in enumerate(faces):
        for v in f:
            incident[v].add(face_id)
        for a, b in zip(f, f[1:] + f[:1]):
            edges[tuple(sorted((a, b)))].append((face_id, a, b))
    actual_boundary = set()
    fan_neighbors = defaultdict(lambda: defaultdict(set))
    for edge, entries in edges.items():
        if len(entries) == 1:
            _, a, b = entries[0]
            actual_boundary.add((a, b))
        elif len(entries) == 2:
            (fi, a, b), (fj, c, d) = entries
            if (a, b) != (d, c):
                raise GeometryError("Internal patch edges have inconsistent winding")
            neighbors[fi].add(fj)
            neighbors[fj].add(fi)
            for v in edge:
                fan_neighbors[v][fi].add(fj)
                fan_neighbors[v][fj].add(fi)
        else:
            raise GeometryError("Patch has a nonmanifold edge")
    expected_boundary = set(zip(loop, loop[1:] + loop[:1]))
    if actual_boundary != expected_boundary:
        raise GeometryError("Declared boundary must match the complete directed patch boundary")

    def reachable(start, adjacency):
        visited = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            for other in adjacency.get(current, ()):
                if other not in visited:
                    visited.add(other)
                    pending.append(other)
        return visited

    if len(reachable(0, neighbors)) != len(faces):
        raise GeometryError("Patch faces must form one connected component")
    for v, face_ids in incident.items():
        if reachable(next(iter(face_ids)), fan_neighbors[v]) != face_ids:
            raise GeometryError(f"Vertex {v} has disconnected face fans")
    if len(points) - len(edges) + len(faces) != 1:
        raise GeometryError("Patch must be a topological disk")
    forward = {"vertices": [list(p) for p in points],
               "triangles": [list(f) for f in faces], "boundary_loop": loop.copy()}
    reverse = {"vertices": [list(p) for p in points],
               "triangles": [[a, c, b] for a, b, c in faces],
               "boundary_loop": [loop[0], *reversed(loop[1:])]}
    return {"forward": forward, "reverse": reverse,
            "vertex_pairs": [[i, i] for i in range(len(points))],
            "triangle_pairs": [[i, i] for i in range(len(faces))],
            "length_tolerance": tolerance, "clearance": 0.0,
            "checks": {"single_oriented_topological_disk": True,
                       "nondegenerate_triangles": True,
                       "self_intersection_tested": False,
                       "shell_collision_tested": False}}
