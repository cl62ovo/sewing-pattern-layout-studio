import argparse
import json
from pathlib import Path

from plush_pattern_studio.geometry.normalize import GeometryInputError, normalize_glb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize and diagnose a local GLB in millimeters."
    )
    parser.add_argument("input_glb", type=Path)
    parser.add_argument("--height-mm", required=True, type=float)
    parser.add_argument("--output-glb", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = normalize_glb(args.input_glb, args.height_mm, args.output_glb)
    except GeometryInputError as error:
        print(json.dumps({"errorCode": error.code, "message": str(error)}))
        return 2

    payload = report.model_dump_json(by_alias=True, indent=2)
    if args.output_json is None:
        print(payload)
    else:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    return 0 if report.stages[0].status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
