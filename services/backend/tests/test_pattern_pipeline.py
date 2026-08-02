from pathlib import Path

import pytest
import trimesh
from pypdf import PdfReader
from pypdf.generic import ContentStream
from reportlab.lib.units import mm

from plush_pattern_studio.contracts.pipeline import StageStatus
from plush_pattern_studio.geometry.normalize import normalize_glb
from plush_pattern_studio.geometry.pattern import MAX_PATTERN_FACES, _load_mesh, build_pattern

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "glb"


def test_dense_pattern_input_is_simplified_as_closed_manifold(tmp_path: Path) -> None:
    model = tmp_path / "dense.glb"
    source = trimesh.creation.icosphere(subdivisions=6)
    source.export(model, file_type="glb")

    mesh = _load_mesh(model)

    assert len(mesh.faces) <= MAX_PATTERN_FACES
    assert mesh.bounds == pytest.approx(source.bounds)
    assert mesh.is_watertight is True
    assert mesh.is_winding_consistent is True


def test_box_builds_scored_vector_pattern_and_pdf(tmp_path: Path) -> None:
    model = tmp_path / "box.glb"
    trimesh.creation.box(extents=[120, 240, 160]).export(model, file_type="glb")

    report = build_pattern(
        model,
        target_height_mm=240,
        seam_allowance_mm=7,
        output_directory=tmp_path / "pattern",
    )

    assert report.quality.passed is True
    assert report.quality.piece_count == 6
    assert report.quality.mean_distortion <= 0.03
    assert report.quality.max_seam_mismatch <= 0.005
    assert report.quality.flipped_triangle_count == 0
    assert report.quality.unpaired_seam_count == 0
    assert all(stage.status == StageStatus.COMPLETED for stage in report.stages)
    assert all(piece.seam_path_mm[0] == piece.seam_path_mm[-1] for piece in report.pieces)
    assert all(piece.cut_path_mm[0] == piece.cut_path_mm[-1] for piece in report.pieces)

    svg = tmp_path / "pattern" / "pattern.svg"
    pdf = tmp_path / "pattern" / "pattern.pdf"
    assert "Experimental pattern" in svg.read_text(encoding="utf-8")
    assert "stroke-dasharray" in svg.read_text(encoding="utf-8")
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert pdf.stat().st_size > 1000
    reader = PdfReader(pdf)
    assert float(reader.pages[0].mediabox.width) == pytest.approx(210 * mm, abs=0.2 * mm)
    assert float(reader.pages[0].mediabox.height) == pytest.approx(297 * mm, abs=0.2 * mm)
    calibration_size = 50 * mm
    content = ContentStream(reader.pages[0]["/Contents"], reader)
    assert any(
        operator == b"re"
        and float(operands[2]) == pytest.approx(calibration_size, abs=0.2 * mm)
        and float(operands[3]) == pytest.approx(calibration_size, abs=0.2 * mm)
        for operands, operator in content.operations
    )


@pytest.mark.parametrize(
    "fixture_name",
    ["rounded-body.glb", "long-ears.glb", "simple-tail.glb"],
)
def test_risk_fixture_meets_pattern_quality_gates(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    normalized = tmp_path / fixture_name
    normalize_glb(
        FIXTURE_DIR / fixture_name,
        target_height_mm=240,
        output_glb=normalized,
    )
    report = build_pattern(
        normalized,
        target_height_mm=240,
        seam_allowance_mm=7,
        output_directory=tmp_path / f"pattern-{fixture_name}",
    )

    assert report.quality.passed is True
    assert report.quality.piece_count <= 12
    assert report.quality.mean_distortion <= 0.03
    assert report.quality.max_seam_mismatch <= 0.005
    assert report.quality.flipped_triangle_count == 0
    assert report.quality.boundary_self_intersection_count == 0
    assert report.quality.unpaired_seam_count == 0
    assert report.pdf_file_name == "pattern.pdf"
