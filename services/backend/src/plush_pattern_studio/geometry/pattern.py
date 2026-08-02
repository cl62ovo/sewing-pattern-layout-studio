from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymeshlab
import trimesh
import xatlas
from pypdf import PdfReader
from pypdf.generic import ContentStream
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from shapely.geometry import Polygon

from plush_pattern_studio.contracts.pipeline import (
    ErrorCode,
    PatternPiece,
    PatternPipelineReport,
    PatternQuality,
    PipelineStage,
    SeamEdge,
    StageReport,
    StageStatus,
)

MAX_PIECES = 12
MAX_PATTERN_FACES = 20_000
PATTERN_VOXEL_RESOLUTION = 64
MAX_MEAN_DISTORTION = 0.03
MAX_SEAM_MISMATCH = 0.005
AREA_EPSILON = 1e-10
ATLAS_RESOLUTION = 4096
ATLAS_TEXELS_PER_UNIT = 1.0
CHART_COST_CANDIDATES = (0.5, 0.25, 0.05)


@dataclass
class _FlattenedCandidate:
    vertex_mapping: np.ndarray
    faces: np.ndarray
    uv_mm: np.ndarray
    mean_distortion: float


class PatternBuildError(ValueError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_mesh(path: Path) -> trimesh.Trimesh:
    try:
        mesh = trimesh.load_scene(path, file_type="glb").to_mesh()
    except Exception as error:
        raise PatternBuildError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Normalized GLB geometry could not be decoded.",
        ) from error
    if mesh.is_empty or not mesh.is_watertight or not mesh.is_winding_consistent:
        raise PatternBuildError(
            ErrorCode.MESH_REPAIR_FAILED,
            "Pattern input must be a closed, consistently wound manifold mesh.",
        )
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) > MAX_PATTERN_FACES:
        source_bounds = mesh.bounds.copy()
        try:
            pitch = float(max(mesh.extents)) / PATTERN_VOXEL_RESOLUTION
            voxels = mesh.voxelized(pitch).fill()
            mesh = voxels.marching_cubes
            mesh.apply_transform(voxels.transform)
            mesh.process(validate=True)
            if len(mesh.faces) > MAX_PATTERN_FACES:
                mesh_set = pymeshlab.MeshSet()
                mesh_set.add_mesh(
                    pymeshlab.Mesh(
                        vertex_matrix=mesh.vertices,
                        face_matrix=mesh.faces,
                    )
                )
                mesh_set.meshing_decimation_quadric_edge_collapse(
                    targetfacenum=MAX_PATTERN_FACES,
                    preservetopology=True,
                    preservenormal=True,
                    autoclean=True,
                )
                simplified = mesh_set.current_mesh()
                mesh = trimesh.Trimesh(
                    vertices=simplified.vertex_matrix(),
                    faces=simplified.face_matrix(),
                    process=True,
                )
            mesh.apply_translation(-mesh.bounds.mean(axis=0))
            mesh.apply_scale((source_bounds[1] - source_bounds[0]) / mesh.extents)
            mesh.apply_translation(source_bounds.mean(axis=0))
        except Exception as error:
            raise PatternBuildError(
                ErrorCode.MESH_REPAIR_FAILED,
                "Pattern input could not be simplified for segmentation.",
            ) from error
        if mesh.is_empty or not mesh.is_watertight or not mesh.is_winding_consistent:
            raise PatternBuildError(
                ErrorCode.MESH_REPAIR_FAILED,
                "Pattern simplification could not preserve a closed manifold mesh.",
            )
    return mesh


def _face_components(faces: np.ndarray) -> list[np.ndarray]:
    adjacency = trimesh.graph.face_adjacency(faces=faces)
    components = trimesh.graph.connected_components(
        adjacency,
        nodes=np.arange(len(faces)),
        min_len=1,
    )
    return sorted(
        (np.asarray(component, dtype=np.int64) for component in components),
        key=lambda component: int(component.min()),
    )


def _ordered_boundary(faces: np.ndarray) -> list[int]:
    edge_counts: dict[tuple[int, int], int] = defaultdict(int)
    for face in faces:
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_counts[tuple(sorted((int(start), int(end))))] += 1
    boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
    neighbors: dict[int, list[int]] = defaultdict(list)
    for start, end in boundary_edges:
        neighbors[start].append(end)
        neighbors[end].append(start)
    if not boundary_edges or any(len(items) != 2 for items in neighbors.values()):
        raise PatternBuildError(
            ErrorCode.SEGMENTATION_NO_VALID_CUT,
            "A parameterized piece does not have one simple disk boundary.",
        )

    start = min(neighbors)
    boundary = [start]
    previous = -1
    current = start
    while True:
        candidates = sorted(item for item in neighbors[current] if item != previous)
        if not candidates:
            break
        following = candidates[0]
        if following == start:
            boundary.append(start)
            break
        if following in boundary:
            raise PatternBuildError(
                ErrorCode.SEGMENTATION_NO_VALID_CUT,
                "A parameterized boundary contains a secondary loop.",
            )
        boundary.append(following)
        previous, current = current, following
    if len(boundary) != len(neighbors) + 1:
        raise PatternBuildError(
            ErrorCode.SEGMENTATION_NO_VALID_CUT,
            "A parameterized piece contains multiple boundary loops.",
        )
    return boundary


def _triangle_area_2d(points: np.ndarray) -> float:
    first, second, third = points
    edge_a = second - first
    edge_b = third - first
    return 0.5 * float(edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0])


def _distortion(vertices_3d: np.ndarray, vertices_2d: np.ndarray) -> tuple[float, float]:
    edge_a = vertices_3d[1] - vertices_3d[0]
    edge_b = vertices_3d[2] - vertices_3d[0]
    length_a = float(np.linalg.norm(edge_a))
    if length_a <= AREA_EPSILON:
        return math.inf, 0.0
    axis_a = edge_a / length_a
    projected = float(np.dot(edge_b, axis_a))
    perpendicular = math.sqrt(max(float(np.dot(edge_b, edge_b)) - projected**2, 0.0))
    if perpendicular <= AREA_EPSILON:
        return math.inf, 0.0
    source_basis = np.array([[length_a, projected], [0.0, perpendicular]])
    target_basis = np.column_stack(
        (vertices_2d[1] - vertices_2d[0], vertices_2d[2] - vertices_2d[0])
    )
    jacobian = target_basis @ np.linalg.inv(source_basis)
    singular_values = np.linalg.svd(jacobian, compute_uv=False)
    value = float(np.max(np.abs(singular_values - 1.0)))
    area = length_a * perpendicular * 0.5
    return value, area


def _local_faces(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_ids: set[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    selected_faces = faces[np.asarray(sorted(face_ids), dtype=np.int64)]
    source_vertex_ids = np.unique(selected_faces)
    inverse = np.full(len(vertices), -1, dtype=np.int64)
    inverse[source_vertex_ids] = np.arange(len(source_vertex_ids))
    return source_vertex_ids, inverse[selected_faces], selected_faces


def _initial_chart_parts(
    vertices: np.ndarray,
    faces: np.ndarray,
    chart_cost: float,
) -> list[set[int]]:
    try:
        atlas = xatlas.Atlas()
        atlas.add_mesh(vertices.astype(np.float32), faces.astype(np.uint32))
        chart_options = xatlas.ChartOptions()
        chart_options.max_cost = chart_cost
        pack_options = xatlas.PackOptions()
        pack_options.resolution = ATLAS_RESOLUTION
        pack_options.texels_per_unit = ATLAS_TEXELS_PER_UNIT
        pack_options.padding = 0
        pack_options.bilinear = False
        pack_options.blockAlign = False
        atlas.generate(chart_options, pack_options)
        vertex_mapping, atlas_faces, _ = atlas[0]
    except Exception as error:
        raise PatternBuildError(
            ErrorCode.SEGMENTATION_NO_VALID_CUT,
            "xatlas could not generate candidate seam charts.",
        ) from error
    if not np.array_equal(vertex_mapping[atlas_faces], faces):
        raise PatternBuildError(
            ErrorCode.SEGMENTATION_NO_VALID_CUT,
            "Candidate chart faces no longer match the source mesh.",
        )
    return [set(map(int, component)) for component in _face_components(atlas_faces)]


def _merge_parts_to_budget(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_adjacency: np.ndarray,
    parts: list[set[int]],
) -> list[set[int]]:
    parts = [set(part) for part in parts]
    while len(parts) > MAX_PIECES:
        face_to_part = {
            face_id: part_index
            for part_index, part in enumerate(parts)
            for face_id in part
        }
        shared_edges: Counter[tuple[int, int]] = Counter()
        for first_face, second_face in face_adjacency:
            first_part = face_to_part[int(first_face)]
            second_part = face_to_part[int(second_face)]
            if first_part != second_part:
                shared_edges[tuple(sorted((first_part, second_part)))] += 1
        candidates = sorted(
            shared_edges,
            key=lambda pair: (
                len(parts[pair[0]]) + len(parts[pair[1]]),
                -shared_edges[pair],
                pair,
            ),
        )
        merged = False
        for first_part, second_part in candidates:
            combined = parts[first_part] | parts[second_part]
            _, local_faces, _ = _local_faces(vertices, faces, combined)
            try:
                _ordered_boundary(local_faces)
            except PatternBuildError:
                continue
            parts[first_part] = combined
            parts.pop(second_part)
            merged = True
            break
        if not merged:
            break
    return parts


def _connected_seam_totals(
    edge_occurrences: dict[tuple[int, int], list[tuple[int, float]]],
) -> list[tuple[tuple[int, int], dict[int, float]]]:
    grouped_edges: dict[
        tuple[int, int],
        list[tuple[tuple[int, int], list[tuple[int, float]]]],
    ] = defaultdict(list)
    for source_key, occurrences in edge_occurrences.items():
        if len(occurrences) != 2:
            continue
        piece_pair = tuple(sorted((occurrences[0][0], occurrences[1][0])))
        grouped_edges[piece_pair].append((source_key, occurrences))

    chains: list[tuple[tuple[int, int], dict[int, float]]] = []
    for piece_pair, edges in grouped_edges.items():
        vertex_neighbors: dict[int, set[int]] = defaultdict(set)
        edge_lookup: dict[tuple[int, int], list[tuple[int, float]]] = {}
        for source_key, occurrences in edges:
            start, end = source_key
            vertex_neighbors[start].add(end)
            vertex_neighbors[end].add(start)
            edge_lookup[source_key] = occurrences
        remaining = set(vertex_neighbors)
        while remaining:
            stack = [remaining.pop()]
            component_vertices: set[int] = set()
            while stack:
                vertex = stack.pop()
                component_vertices.add(vertex)
                for neighbor in vertex_neighbors[vertex]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
            totals = {piece_pair[0]: 0.0, piece_pair[1]: 0.0}
            for (start, end), occurrences in edge_lookup.items():
                if start not in component_vertices or end not in component_vertices:
                    continue
                for piece_index, length in occurrences:
                    totals[piece_index] += length
            chains.append((piece_pair, totals))
    return chains


def _seam_walk_targets(
    edge_occurrences: dict[tuple[int, int], list[tuple[int, float]]],
) -> dict[tuple[int, tuple[int, int]], float]:
    grouped_edges: dict[
        tuple[int, int],
        list[tuple[tuple[int, int], list[tuple[int, float]]]],
    ] = defaultdict(list)
    for source_key, occurrences in edge_occurrences.items():
        if len(occurrences) == 2:
            pair = tuple(sorted((occurrences[0][0], occurrences[1][0])))
            grouped_edges[pair].append((source_key, occurrences))

    targets: dict[tuple[int, tuple[int, int]], float] = {}
    for piece_pair, edges in grouped_edges.items():
        vertex_neighbors: dict[int, set[int]] = defaultdict(set)
        for (start, end), _ in edges:
            vertex_neighbors[start].add(end)
            vertex_neighbors[end].add(start)
        remaining = set(vertex_neighbors)
        while remaining:
            stack = [remaining.pop()]
            component_vertices: set[int] = set()
            while stack:
                vertex = stack.pop()
                component_vertices.add(vertex)
                for neighbor in vertex_neighbors[vertex]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
            component_edges = [
                item
                for item in edges
                if item[0][0] in component_vertices and item[0][1] in component_vertices
            ]
            totals = {piece_pair[0]: 0.0, piece_pair[1]: 0.0}
            for _, occurrences in component_edges:
                for piece_index, length in occurrences:
                    totals[piece_index] += length
            target_total = sum(totals.values()) * 0.5
            scales = {
                piece_index: target_total / max(total, AREA_EPSILON)
                for piece_index, total in totals.items()
            }
            for source_key, occurrences in component_edges:
                for piece_index, length in occurrences:
                    targets[(piece_index, source_key)] = length * scales[piece_index]
    return targets


def _walk_seam_boundary(
    source_vertex_ids: np.ndarray,
    local_faces: np.ndarray,
    uv: np.ndarray,
    chart_index: int,
    target_by_edge: dict[tuple[int, tuple[int, int]], float],
) -> None:
    boundary = np.asarray(_ordered_boundary(local_faces)[:-1], dtype=np.int64)
    original = uv[boundary].copy()
    following = np.roll(np.arange(len(boundary)), -1)
    target_lengths = np.asarray(
        [
            target_by_edge[
                (
                    chart_index,
                    tuple(
                        sorted(
                            (
                                int(source_vertex_ids[boundary[index]]),
                                int(source_vertex_ids[boundary[following[index]]]),
                            )
                        )
                    ),
                )
            ]
            for index in range(len(boundary))
        ]
    )
    mean_length = max(float(np.mean(target_lengths)), AREA_EPSILON)

    def residual(values: np.ndarray) -> np.ndarray:
        points = values.reshape((-1, 2))
        edge_lengths = np.linalg.norm(points[following] - points, axis=1)
        edge_error = (edge_lengths - target_lengths) / target_lengths
        position_error = ((points - original) / mean_length).ravel()
        return np.concatenate((1000.0 * edge_error, 0.02 * position_error))

    variable_count = len(boundary) * 2
    sparsity = lil_matrix((len(boundary) + variable_count, variable_count), dtype=int)
    for edge_index, next_index in enumerate(following):
        sparsity[edge_index, edge_index * 2 : edge_index * 2 + 2] = 1
        sparsity[edge_index, next_index * 2 : next_index * 2 + 2] = 1
    for variable_index in range(variable_count):
        sparsity[len(boundary) + variable_index, variable_index] = 1
    result = least_squares(
        residual,
        original.ravel(),
        jac_sparsity=sparsity.tocsr(),
        max_nfev=300,
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
    )
    adjusted = result.x.reshape((-1, 2))
    relative_errors = np.abs(
        np.linalg.norm(adjusted[following] - adjusted, axis=1) - target_lengths
    ) / target_lengths
    if float(np.max(relative_errors)) > MAX_SEAM_MISMATCH:
        raise PatternBuildError(
            ErrorCode.SEAM_LENGTH_MISMATCH,
            "Seam walking could not meet the paired length tolerance.",
        )
    uv[boundary] = adjusted


def _parameterize_parts(
    vertices: np.ndarray,
    faces: np.ndarray,
    parts: list[set[int]],
    seam_allowance_mm: float,
) -> _FlattenedCandidate:
    mappings: list[np.ndarray] = []
    flattened_faces: list[np.ndarray] = []
    flattened_uvs: list[np.ndarray] = []
    chart_ranges: list[tuple[int, int]] = []
    total_area = 0.0
    seam_occurrences: dict[tuple[int, int], list[tuple[int, float]]] = defaultdict(list)
    vertex_offset = 0
    for chart_index, part in enumerate(sorted(parts, key=lambda item: min(item))):
        source_vertex_ids, local_faces, _ = _local_faces(vertices, faces, part)
        boundary = _ordered_boundary(local_faces)
        try:
            mesh_set = pymeshlab.MeshSet()
            mesh_set.add_mesh(
                pymeshlab.Mesh(
                    vertex_matrix=vertices[source_vertex_ids],
                    face_matrix=local_faces,
                )
            )
            mesh_set.apply_filter(
                "compute_texcoord_parametrization_least_squares_conformal_maps"
            )
            uv = np.asarray(
                mesh_set.current_mesh().vertex_tex_coord_matrix(), dtype=np.float64
            )
        except Exception as error:
            raise PatternBuildError(
                ErrorCode.SEGMENTATION_NO_VALID_CUT,
                "LSCM could not flatten a candidate disk chart.",
            ) from error
        if uv.shape != (len(source_vertex_ids), 2) or not np.all(np.isfinite(uv)):
            raise PatternBuildError(
                ErrorCode.SEGMENTATION_NO_VALID_CUT,
                "LSCM returned invalid two-dimensional coordinates.",
            )
        source_triangles = vertices[source_vertex_ids][local_faces]
        source_areas = trimesh.triangles.area(source_triangles)
        flat_triangles = np.column_stack([uv, np.zeros(len(uv))])[local_faces]
        flat_area = float(np.sum(trimesh.triangles.area(flat_triangles)))
        if flat_area <= AREA_EPSILON:
            raise PatternBuildError(
                ErrorCode.SEGMENTATION_NO_VALID_CUT,
                "LSCM returned a zero-area chart.",
            )
        uv *= math.sqrt(float(np.sum(source_areas)) / flat_area)
        total_area += float(np.sum(source_areas))
        for boundary_index in range(len(boundary) - 1):
            local_start, local_end = boundary[boundary_index : boundary_index + 2]
            source_key = tuple(
                sorted(
                    (
                        int(source_vertex_ids[local_start]),
                        int(source_vertex_ids[local_end]),
                    )
                )
            )
            length = float(np.linalg.norm(uv[local_end] - uv[local_start]))
            seam_occurrences[source_key].append((chart_index, length))
        mappings.append(source_vertex_ids.astype(np.uint32))
        flattened_faces.append(local_faces.astype(np.uint32) + vertex_offset)
        flattened_uvs.append(uv)
        chart_ranges.append((vertex_offset, vertex_offset + len(uv)))
        vertex_offset += len(uv)

    equations: list[np.ndarray] = []
    targets: list[float] = []
    for (first_chart, second_chart), totals in _connected_seam_totals(
        seam_occurrences
    ):
        if totals[first_chart] <= AREA_EPSILON or totals[second_chart] <= AREA_EPSILON:
            continue
        equation = np.zeros(len(flattened_uvs))
        equation[first_chart] = 1.0
        equation[second_chart] = -1.0
        equations.append(equation)
        targets.append(math.log(totals[second_chart] / totals[first_chart]))
    if equations:
        equations.append(np.ones(len(flattened_uvs)))
        targets.append(0.0)
        corrections = np.linalg.lstsq(
            np.vstack(equations), np.asarray(targets), rcond=None
        )[0]
        for chart_index, correction in enumerate(corrections):
            flattened_uvs[chart_index] *= math.exp(float(correction))

    adjusted_occurrences: dict[tuple[int, int], list[tuple[int, float]]] = defaultdict(list)
    for chart_index, (source_vertex_ids, local_faces, uv) in enumerate(
        zip(mappings, flattened_faces, flattened_uvs, strict=True)
    ):
        local_faces = local_faces - int(local_faces.min())
        boundary = _ordered_boundary(local_faces)
        for edge_index in range(len(boundary) - 1):
            local_start, local_end = boundary[edge_index : edge_index + 2]
            source_key = tuple(
                sorted(
                    (
                        int(source_vertex_ids[local_start]),
                        int(source_vertex_ids[local_end]),
                    )
                )
            )
            length = float(np.linalg.norm(uv[local_end] - uv[local_start]))
            adjusted_occurrences[source_key].append((chart_index, length))
    walk_targets = _seam_walk_targets(adjusted_occurrences)

    weighted_distortion = 0.0
    for chart_index, (source_vertex_ids, local_faces, uv) in enumerate(
        zip(mappings, flattened_faces, flattened_uvs, strict=True)
    ):
        local_faces = local_faces - int(local_faces.min())
        _walk_seam_boundary(
            source_vertex_ids,
            local_faces,
            uv,
            chart_index,
            walk_targets,
        )
        source_triangles = vertices[source_vertex_ids][local_faces]
        source_areas = trimesh.triangles.area(source_triangles)
        for source_triangle, flat_face, area in zip(
            source_triangles, local_faces, source_areas, strict=True
        ):
            distortion, _ = _distortion(source_triangle, uv[flat_face])
            weighted_distortion += distortion * float(area)

    packed_uv = np.vstack(flattened_uvs)
    gap = 2 * seam_allowance_mm + 10.0
    packing_width = max(190.0, math.sqrt(total_area) * 1.5)
    cursor_x = gap
    cursor_y = gap
    row_height = 0.0
    for start, end in chart_ranges:
        chart = packed_uv[start:end]
        chart -= np.min(chart, axis=0)
        chart_size = np.max(chart, axis=0)
        if cursor_x > gap and cursor_x + chart_size[0] + gap > packing_width:
            cursor_x = gap
            cursor_y += row_height + gap
            row_height = 0.0
        chart += np.array([cursor_x, cursor_y])
        cursor_x += float(chart_size[0]) + gap
        row_height = max(row_height, float(chart_size[1]))
    return _FlattenedCandidate(
        vertex_mapping=np.concatenate(mappings),
        faces=np.vstack(flattened_faces),
        uv_mm=packed_uv,
        mean_distortion=weighted_distortion / total_area,
    )


def _build_flattened_candidate(
    mesh: trimesh.Trimesh,
    seam_allowance_mm: float,
) -> _FlattenedCandidate:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    candidates: list[_FlattenedCandidate] = []
    for chart_cost in CHART_COST_CANDIDATES:
        parts = _initial_chart_parts(vertices, faces, chart_cost)
        parts = _merge_parts_to_budget(vertices, faces, mesh.face_adjacency, parts)
        if len(parts) > MAX_PIECES:
            continue
        candidate = _parameterize_parts(vertices, faces, parts, seam_allowance_mm)
        candidates.append(candidate)
        if candidate.mean_distortion <= MAX_MEAN_DISTORTION:
            return candidate
    if not candidates:
        raise PatternBuildError(
            ErrorCode.SEGMENTATION_NO_VALID_CUT,
            "No candidate seam plan could be reduced to twelve disk pieces.",
        )
    return min(candidates, key=lambda candidate: candidate.mean_distortion)


def _score_seam_chains(
    boundary_occurrences: dict[
        tuple[int, int], list[tuple[int, int, float]]
    ],
) -> tuple[float, int]:
    unpaired_seams = 0
    simple_occurrences: dict[tuple[int, int], list[tuple[int, float]]] = {}
    for source_key, occurrences in boundary_occurrences.items():
        if len(occurrences) != 2:
            unpaired_seams += len(occurrences)
        simple_occurrences[source_key] = [
            (piece_index, length) for piece_index, _, length in occurrences
        ]

    max_mismatch = 0.0
    for piece_pair, lengths in _connected_seam_totals(simple_occurrences):
        denominator = max(lengths.values())
        if denominator > AREA_EPSILON:
            mismatch = abs(lengths[piece_pair[0]] - lengths[piece_pair[1]]) / denominator
            max_mismatch = max(max_mismatch, mismatch)
    return max_mismatch, unpaired_seams


def _path_data(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    commands = [f"M {points[0][0]:.4f} {points[0][1]:.4f}"]
    commands.extend(f"L {x:.4f} {y:.4f}" for x, y in points[1:])
    commands.append("Z")
    return " ".join(commands)


def _write_svg(path: Path, pieces: list[PatternPiece], passed: bool) -> None:
    all_points = [point for piece in pieces for point in piece.cut_path_mm]
    width = max((point[0] for point in all_points), default=100.0) + 10.0
    height = max((point[1] for point in all_points), default=100.0) + 18.0
    status = "QUALITY PASSED" if passed else "DIAGNOSTIC ONLY - QUALITY FAILED"
    rows = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.4f}mm" height="{height:.4f}mm" viewBox="0 0 {width:.4f} {height:.4f}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="5" y="8" font-family="sans-serif" font-size="4">Experimental pattern / {status}</text>',
        '<g transform="translate(0 12)" fill="none" stroke="black">',
    ]
    for piece in pieces:
        rows.append(
            f'<path id="{piece.id}-cut" d="{_path_data(piece.cut_path_mm)}" stroke-width="0.35"/>'
        )
        rows.append(
            f'<path id="{piece.id}-seam" d="{_path_data(piece.seam_path_mm)}" stroke-width="0.25" stroke-dasharray="2 1"/>'
        )
        center = np.mean(np.asarray(piece.seam_path_mm[:-1]), axis=0)
        rows.append(
            f'<text x="{center[0]:.4f}" y="{center[1]:.4f}" fill="black" stroke="none" font-family="sans-serif" font-size="3">{piece.name} x{piece.quantity}</text>'
        )
    rows.extend(["</g>", "</svg>"])
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _draw_pdf_path(canvas: Canvas, points: list[tuple[float, float]], offset: tuple[float, float]) -> None:
    path = canvas.beginPath()
    first_x, first_y = points[0]
    path.moveTo((first_x - offset[0] + 10) * mm, (first_y - offset[1] + 10) * mm)
    for x, y in points[1:]:
        path.lineTo((x - offset[0] + 10) * mm, (y - offset[1] + 10) * mm)
    path.close()
    canvas.drawPath(path, stroke=1, fill=0)


def _write_pdf(path: Path, pieces: list[PatternPiece]) -> None:
    page_width_mm = A4[0] / mm
    page_height_mm = A4[1] / mm
    tile_width = page_width_mm - 20
    tile_height = page_height_mm - 30
    all_points = [point for piece in pieces for point in piece.cut_path_mm]
    pattern_width = max((point[0] for point in all_points), default=0.0)
    pattern_height = max((point[1] for point in all_points), default=0.0)
    columns = max(1, math.ceil(pattern_width / tile_width))
    rows = max(1, math.ceil(pattern_height / tile_height))

    canvas = Canvas(str(path), pagesize=A4, pageCompression=1)
    canvas.setTitle("Experimental plush sewing pattern")
    canvas.setAuthor("Plush Pattern Studio")
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(20 * mm, 272 * mm, "Experimental pattern / 100% Actual size")
    canvas.setFont("Helvetica", 9)
    canvas.drawString(20 * mm, 264 * mm, "Calibration page")
    canvas.rect(20 * mm, 195 * mm, 50 * mm, 50 * mm, stroke=1, fill=0)
    canvas.drawString(20 * mm, 190 * mm, "50 x 50 mm calibration square")
    canvas.showPage()

    page_number = 1
    for row in range(rows):
        for column in range(columns):
            page_number += 1
            offset = (column * tile_width, row * tile_height)
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawString(10 * mm, 284 * mm, "Experimental pattern / 100% Actual size")
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(
                200 * mm,
                284 * mm,
                f"Page {page_number} - row {row + 1}, column {column + 1}",
            )
            for piece in pieces:
                bounds = Polygon(piece.cut_path_mm).bounds
                viewport = (
                    offset[0],
                    offset[1],
                    offset[0] + tile_width,
                    offset[1] + tile_height,
                )
                if bounds[2] < viewport[0] or bounds[0] > viewport[2] or bounds[3] < viewport[1] or bounds[1] > viewport[3]:
                    continue
                canvas.setLineWidth(0.35 * mm)
                canvas.setDash()
                _draw_pdf_path(canvas, piece.cut_path_mm, offset)
                canvas.setLineWidth(0.25 * mm)
                canvas.setDash(2 * mm, 1 * mm)
                _draw_pdf_path(canvas, piece.seam_path_mm, offset)
            canvas.showPage()
    canvas.save()
    payload = path.read_bytes()
    if not payload.startswith(b"%PDF-") or len(payload) < 1000:
        raise PatternBuildError(ErrorCode.PDF_VALIDATION_FAILED, "PDF output is invalid.")
    try:
        reader = PdfReader(path)
        tolerance_points = 0.2 * mm
        if len(reader.pages) < 2:
            raise ValueError("PDF is missing pattern pages.")
        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if abs(width - A4[0]) > tolerance_points or abs(height - A4[1]) > tolerance_points:
                raise ValueError("PDF page is not A4.")
        calibration_size = 50 * mm
        content = ContentStream(reader.pages[0]["/Contents"], reader)
        has_calibration_square = any(
            operator == b"re"
            and len(operands) == 4
            and abs(float(operands[2]) - calibration_size) <= tolerance_points
            and abs(float(operands[3]) - calibration_size) <= tolerance_points
            for operands, operator in content.operations
        )
        if not has_calibration_square:
            raise ValueError("PDF calibration square is missing or incorrectly sized.")
    except Exception as error:
        path.unlink(missing_ok=True)
        raise PatternBuildError(
            ErrorCode.PDF_VALIDATION_FAILED,
            "PDF page or calibration dimensions failed validation.",
        ) from error


def build_pattern(
    normalized_glb: Path,
    *,
    target_height_mm: float,
    seam_allowance_mm: float,
    output_directory: Path,
) -> PatternPipelineReport:
    if not math.isfinite(seam_allowance_mm) or seam_allowance_mm < 0:
        raise PatternBuildError(
            ErrorCode.SEAM_ALLOWANCE_OFFSET_FAILED,
            "Seam allowance must be a finite non-negative millimeter value.",
        )
    mesh = _load_mesh(normalized_glb)
    if not math.isclose(
        float(mesh.extents[1]),
        target_height_mm,
        rel_tol=1e-4,
        abs_tol=0.2,
    ):
        raise PatternBuildError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Pattern input height does not match the requested millimeter height.",
        )
    source_sha256 = hashlib.sha256(normalized_glb.read_bytes()).hexdigest()
    candidate = _build_flattened_candidate(mesh, seam_allowance_mm)
    vertex_mapping = candidate.vertex_mapping
    atlas_faces = candidate.faces
    atlas_uv_mm = candidate.uv_mm
    components = _face_components(np.asarray(atlas_faces, dtype=np.int64))

    piece_records: list[dict[str, object]] = []
    boundary_occurrences: dict[tuple[int, int], list[tuple[int, int, float]]] = defaultdict(list)
    self_intersections = 0
    flipped_triangles = 0
    weighted_distortion = 0.0
    total_area = 0.0
    max_distortion = 0.0

    for piece_index, face_ids in enumerate(components, start=1):
        component_faces = np.asarray(atlas_faces[face_ids], dtype=np.int64)
        boundary = _ordered_boundary(component_faces)
        seam_path = [tuple(float(value) for value in atlas_uv_mm[index]) for index in boundary]
        polygon = Polygon(seam_path)
        if not polygon.is_valid or polygon.is_empty or polygon.area <= AREA_EPSILON:
            self_intersections += 1
            cut_path = seam_path
        else:
            cut = polygon.buffer(seam_allowance_mm, join_style="round")
            if cut.geom_type != "Polygon" or not cut.is_valid or cut.is_empty:
                raise PatternBuildError(
                    ErrorCode.SEAM_ALLOWANCE_OFFSET_FAILED,
                    f"Seam allowance offset failed for piece {piece_index}.",
                )
            cut_path = [tuple(float(value) for value in point) for point in cut.exterior.coords]

        used_vertices = sorted({int(index) for face in component_faces for index in face})
        local_index = {global_index: index for index, global_index in enumerate(used_vertices)}
        local_faces = [tuple(local_index[int(index)] for index in face) for face in component_faces]
        local_uv = [tuple(float(value) for value in atlas_uv_mm[index]) for index in used_vertices]
        source_vertex_ids = [int(vertex_mapping[index]) for index in used_vertices]

        signs: list[float] = []
        for face_id in face_ids:
            atlas_face = np.asarray(atlas_faces[face_id], dtype=np.int64)
            mapped_face = np.asarray(vertex_mapping[atlas_face], dtype=np.int64)
            distortion, area = _distortion(
                np.asarray(mesh.vertices)[mapped_face],
                atlas_uv_mm[atlas_face],
            )
            weighted_distortion += distortion * area
            total_area += area
            max_distortion = max(max_distortion, distortion)
            signs.append(_triangle_area_2d(atlas_uv_mm[atlas_face]))
        orientation = 1.0 if sum(sign >= 0 for sign in signs) >= len(signs) / 2 else -1.0
        flipped_triangles += sum(sign * orientation <= AREA_EPSILON for sign in signs)

        for boundary_index in range(len(boundary) - 1):
            atlas_start = boundary[boundary_index]
            atlas_end = boundary[boundary_index + 1]
            source_start = int(vertex_mapping[atlas_start])
            source_end = int(vertex_mapping[atlas_end])
            source_key = tuple(sorted((source_start, source_end)))
            length_2d = float(np.linalg.norm(atlas_uv_mm[atlas_end] - atlas_uv_mm[atlas_start]))
            boundary_occurrences[source_key].append((piece_index - 1, boundary_index, length_2d))

        piece_records.append(
            {
                "id": f"piece-{piece_index}",
                "name": f"Piece {piece_index}",
                "source_vertex_ids": source_vertex_ids,
                "faces": local_faces,
                "vertices_2d_mm": local_uv,
                "seam_path_mm": seam_path,
                "cut_path_mm": cut_path,
                "seam_edges": [],
            }
        )

    max_seam_mismatch, unpaired_seams = _score_seam_chains(boundary_occurrences)
    for source_key, occurrences in boundary_occurrences.items():
        source_length = float(
            np.linalg.norm(np.asarray(mesh.vertices)[source_key[1]] - np.asarray(mesh.vertices)[source_key[0]])
        )
        for occurrence_index, (piece_index, edge_index, length_2d) in enumerate(occurrences):
            edge_id = f"piece-{piece_index + 1}/seam/{edge_index + 1}"
            if len(occurrences) == 2:
                other = occurrences[1 - occurrence_index]
                pair_id = f"piece-{other[0] + 1}/seam/{other[1] + 1}"
            else:
                pair_id = "unpaired"
            seam_edges = piece_records[piece_index]["seam_edges"]
            assert isinstance(seam_edges, list)
            seam_edges.append(
                SeamEdge(
                    id=edge_id,
                    pairId=pair_id,
                    sourceVertices=source_key,
                    length3dMm=source_length,
                    length2dMm=length_2d,
                )
            )

    pieces = [PatternPiece.model_validate(record) for record in piece_records]
    mean_distortion = weighted_distortion / total_area if total_area else math.inf
    failure_reasons: list[ErrorCode] = []
    if len(pieces) > MAX_PIECES:
        failure_reasons.append(ErrorCode.SEGMENTATION_NO_VALID_CUT)
    if flipped_triangles:
        failure_reasons.append(ErrorCode.FLATTENING_FLIPPED_TRIANGLES)
    if mean_distortion > MAX_MEAN_DISTORTION or self_intersections:
        failure_reasons.append(ErrorCode.FLATTENING_DISTORTION_TOO_HIGH)
    if max_seam_mismatch > MAX_SEAM_MISMATCH or unpaired_seams:
        failure_reasons.append(ErrorCode.SEAM_LENGTH_MISMATCH)
    passed = not failure_reasons

    quality = PatternQuality(
        pieceCount=len(pieces),
        meanDistortion=mean_distortion,
        maxDistortion=max_distortion,
        maxSeamMismatch=max_seam_mismatch,
        flippedTriangleCount=flipped_triangles,
        boundarySelfIntersectionCount=self_intersections,
        unpairedSeamCount=unpaired_seams,
        passed=passed,
        failureReasons=failure_reasons,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    svg_path = output_directory / "pattern.svg"
    _write_svg(svg_path, pieces, passed)
    pdf_name: str | None = None
    if passed:
        pdf_path = output_directory / "pattern.pdf"
        _write_pdf(pdf_path, pieces)
        pdf_name = pdf_path.name

    flatten_error = next(
        (reason for reason in failure_reasons if reason in {ErrorCode.FLATTENING_FLIPPED_TRIANGLES, ErrorCode.FLATTENING_DISTORTION_TOO_HIGH}),
        None,
    )
    score_error = ErrorCode.SEAM_LENGTH_MISMATCH if ErrorCode.SEAM_LENGTH_MISMATCH in failure_reasons else None
    stages = [
        StageReport(
            stage=PipelineStage.SEGMENT,
            status=StageStatus.FAILED if len(pieces) > MAX_PIECES else StageStatus.COMPLETED,
            errorCode=ErrorCode.SEGMENTATION_NO_VALID_CUT if len(pieces) > MAX_PIECES else None,
        ),
        StageReport(
            stage=PipelineStage.FLATTEN,
            status=StageStatus.FAILED if flatten_error else StageStatus.COMPLETED,
            errorCode=flatten_error,
        ),
        StageReport(
            stage=PipelineStage.SCORE,
            status=StageStatus.FAILED if failure_reasons else StageStatus.COMPLETED,
            errorCode=score_error or (failure_reasons[0] if failure_reasons else None),
        ),
        StageReport(
            stage=PipelineStage.PDF,
            status=StageStatus.COMPLETED if passed else StageStatus.FAILED,
            errorCode=None if passed else failure_reasons[0],
        ),
    ]
    return PatternPipelineReport(
        sourceSha256=source_sha256,
        targetHeightMm=target_height_mm,
        seamAllowanceMm=seam_allowance_mm,
        pieces=pieces,
        quality=quality,
        stages=stages,
        svgFileName=svg_path.name,
        pdfFileName=pdf_name,
    )
