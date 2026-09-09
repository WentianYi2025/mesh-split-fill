"""Read-only mesh topology inspection. Invoke through runtime.py inside Blender."""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def script_arguments():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def import_file(source):
    suffix = source.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
        return
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    def invoke(name, label, **kwargs):
        operator = getattr(bpy.ops.wm, name, None)
        if operator is None:
            raise RuntimeError("%s import operator is unavailable in this Blender build" % label)
        properties = {prop.identifier for prop in operator.get_rna_type().properties}
        missing = sorted(set(kwargs) - properties)
        if missing:
            raise RuntimeError("%s import operator lacks required safe options: %s" % (label, ", ".join(missing)))
        operator(**kwargs)

    # Blender 4.2+ native importers: these axes preserve OBJ/STL/PLY XYZ
    # coordinates, and validation/merge/scale behaviours are disabled explicitly.
    if suffix == ".obj":
        invoke("obj_import", "OBJ", filepath=str(source), global_scale=1.0,
               forward_axis="Y", up_axis="Z", validate_meshes=False)
    elif suffix == ".stl":
        invoke("stl_import", "STL", filepath=str(source), global_scale=1.0,
               use_scene_unit=False, forward_axis="Y", up_axis="Z", use_mesh_validate=False)
    elif suffix == ".ply":
        invoke("ply_import", "PLY", filepath=str(source), global_scale=1.0,
               use_scene_unit=False, forward_axis="Y", up_axis="Z", merge_verts=False)
    else:
        raise RuntimeError("Unsupported input extension: %s (expected .obj, .blend, .stl, or .ply)" % suffix)


def matrix_rows(matrix):
    return [[float(item) for item in row] for row in matrix]


def mesh_report(obj):
    mesh = obj.data
    vertices = mesh.vertices
    if vertices:
        local_points = [vertex.co.copy() for vertex in vertices]
        world_points = [obj.matrix_world @ point for point in local_points]
        local_min = [min(point[i] for point in local_points) for i in range(3)]
        local_max = [max(point[i] for point in local_points) for i in range(3)]
        world_min = [min(point[i] for point in world_points) for i in range(3)]
        world_max = [max(point[i] for point in world_points) for i in range(3)]
        extent = max((local_max[i] - local_min[i] for i in range(3)), default=0.0)
    else:
        local_min = local_max = world_min = world_max = [0.0, 0.0, 0.0]
        extent = 0.0
    # A scale-relative tolerance avoids a fixed world-unit threshold.  A mesh
    # with zero local extent has no meaningful scale, so only exactly-zero area
    # faces are degenerate in that case.
    if extent > 0.0:
        area_tolerance = extent * extent * 1e-12
        degenerate = sum(1 for polygon in mesh.polygons if polygon.area <= area_tolerance)
        tolerance_mode = "extent_squared_relative"
    else:
        area_tolerance = 0.0
        degenerate = sum(1 for polygon in mesh.polygons if polygon.area <= 0.0)
        tolerance_mode = "zero_extent_exact_area"
    face_counts = {tuple(sorted(edge.vertices[:])): 0 for edge in mesh.edges}
    for polygon in mesh.polygons:
        for edge_key in polygon.edge_keys:
            face_counts[tuple(sorted(edge_key))] += 1
    edge_face_counts = [face_counts[tuple(sorted(edge.vertices[:]))] for edge in mesh.edges]
    boundary_edges = [edge for edge in mesh.edges if face_counts[tuple(sorted(edge.vertices[:]))] == 1]
    degrees = {}
    adjacency = {}
    for edge in boundary_edges:
        a, b = edge.vertices[:]
        degrees[a] = degrees.get(a, 0) + 1
        degrees[b] = degrees.get(b, 0) + 1
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    visited, loops = set(), 0
    for start in adjacency:
        if start in visited:
            continue
        stack, component, all_degree_two = [start], [], True
        while stack:
            vertex = stack.pop()
            if vertex in visited:
                continue
            visited.add(vertex)
            component.append(vertex)
            all_degree_two = all_degree_two and degrees[vertex] == 2
            stack.extend(adjacency[vertex] - visited)
        if all_degree_two and len(component) >= 3:
            loops += 1
    return {
        "name": obj.name,
        "type": obj.type,
        "matrix_world": matrix_rows(obj.matrix_world),
        "vertex_count": len(vertices), "face_count": len(mesh.polygons), "edge_count": len(mesh.edges),
        "aabb_local": {"min": local_min, "max": local_max},
        "aabb_world": {"min": world_min, "max": world_max},
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        "topology": {
            "boundary_edge_count": len(boundary_edges), "boundary_loop_count": loops,
            "boundary_branch_vertex_count": sum(1 for degree in degrees.values() if degree > 2),
            "boundary_endpoint_count": sum(1 for degree in degrees.values() if degree == 1),
            "non_manifold_edge_count": sum(1 for count in edge_face_counts if count != 2),
            "degenerate_face_count": degenerate, "degenerate_area_tolerance_local": area_tolerance,
            "degenerate_tolerance_mode": tolerance_mode,
            "self_intersection": "not_checked",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(script_arguments())
    source, output = Path(args.input).expanduser().resolve(), Path(args.output).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError("Input does not exist: %s" % source)
    if source == output:
        raise RuntimeError("Refusing to overwrite the source file")
    import_file(source)
    objects = []
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            objects.append(mesh_report(obj))
        else:
            objects.append({"name": obj.name, "type": obj.type, "matrix_world": matrix_rows(obj.matrix_world)})
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            json.dump({"input": str(source), "objects": objects,
                       "self_intersection": "not_checked",
                       "scope": "Topology-only inspection; this is not final geometric QA."}, handle, ensure_ascii=False, indent=2)
    except FileExistsError as exc:
        raise RuntimeError("Refusing to overwrite an existing output path: %s" % output) from exc


if __name__ == "__main__":
    main()
