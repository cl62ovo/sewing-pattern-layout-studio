import argparse
import json
from pathlib import Path

from plush_pattern_studio.geometry.pattern import PatternBuildError, build_pattern
from plush_pattern_studio.geometry.normalize import GeometryInputError, normalize_glb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize, segment, flatten, score, and export a local GLB pattern."
    )
    parser.add_argument("input_glb", type=Path)
    parser.add_argument("--height-mm", required=True, type=float)
    parser.add_argument("--seam-allowance-mm", default=7.0, type=float)
    parser.add_argument("--output-glb", type=Path)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    normalized_path = args.output_glb
    if args.output_directory is not None and normalized_path is None:
        normalized_path = args.output_directory / "normalized.glb"
    try:
        report = normalize_glb(args.input_glb, args.height_mm, normalized_path)
        pattern_report = None
        if report.stages[0].status == "completed" and args.output_directory is not None:
            if normalized_path is None:
                raise RuntimeError("Normalized output path was not configured.")
            pattern_report = build_pattern(
                normalized_path,
                target_height_mm=args.height_mm,
                seam_allowance_mm=args.seam_allowance_mm,
                output_directory=args.output_directory,
            )
    except (GeometryInputError, PatternBuildError) as error:
        print(json.dumps({"errorCode": error.code, "message": str(error)}))
        return 2

    if pattern_report is None:
        payload = report.model_dump_json(by_alias=True, indent=2)
        succeeded = report.stages[0].status == "completed"
    else:
        payload = json.dumps(
            {
                "normalization": report.model_dump(mode="json", by_alias=True),
                "pattern": pattern_report.model_dump(mode="json", by_alias=True),
            },
            indent=2,
        )
        succeeded = pattern_report.quality.passed
    if args.output_json is None:
        print(payload)
    else:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    return 0 if succeeded else 2


if __name__ == "__main__":
    raise SystemExit(main())
