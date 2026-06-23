#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _copy(src: Path, dst: Path) -> None:
	assert src.exists(), f"Missing source file: {src}"
	dst.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(src, dst)


def normalize(run_dir: Path) -> dict[str, Any]:
	source_dir = run_dir / "02-source-capture"
	media_dir = source_dir / "youtube-media"
	manifest_path = media_dir / "media_manifest.json"
	manifest = _read_json(manifest_path)
	transcript = manifest.get("transcript") if isinstance(manifest.get("transcript"), dict) else {}
	transcript_txt = Path(str(transcript.get("txt_path") or ""))
	transcript_json = Path(str(transcript.get("json_path") or ""))
	metadata_path = media_dir / "metadata.json"
	thumbnail_path = media_dir / "source.jpg"

	_copy(metadata_path, source_dir / "source_metadata.json")
	_copy(transcript_txt, source_dir / "source_transcript.en.txt")
	_copy(transcript_json, source_dir / "source_transcript.en.json")
	_copy(thumbnail_path, source_dir / "thumbnail.jpg")

	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	node = run_manifest.setdefault("nodes", {}).setdefault("02-source-capture", {})
	node["normalized_outputs"] = {
		"status": "pass",
		"source_metadata": str(source_dir / "source_metadata.json"),
		"source_transcript_en_txt": str(source_dir / "source_transcript.en.txt"),
		"source_transcript_en_json": str(source_dir / "source_transcript.en.json"),
		"thumbnail": str(source_dir / "thumbnail.jpg"),
	}
	_write_json(run_manifest_path, run_manifest)
	return node["normalized_outputs"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Normalize 02 source capture outputs for the podcast agent.")
	parser.add_argument("--run-dir", required=True, type=Path)
	args = parser.parse_args()
	result = normalize(args.run_dir.expanduser().resolve())
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
