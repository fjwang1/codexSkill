#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _ffprobe_image(path: Path) -> dict[str, Any]:
	result = subprocess.run([
		"ffprobe",
		"-v",
		"error",
		"-select_streams",
		"v:0",
		"-show_entries",
		"stream=width,height,codec_name",
		"-of",
		"json",
		str(path),
	], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	data = json.loads(result.stdout)
	streams = data.get("streams") or []
	assert streams, f"No image stream in {path}"
	return streams[0]


def _candidate_paths(generated_dir: Path, beat: str) -> list[Path]:
	patterns = [
		f"shot_{beat}.png",
		f"shot_{beat}.jpg",
		f"shot_{beat}.jpeg",
		f"shot_{beat}_*.png",
		f"shot_{beat}_*.jpg",
		f"{beat}.png",
		f"{beat}_*.png",
	]
	paths: list[Path] = []
	for pattern in patterns:
		paths.extend(Path(item) for item in glob.glob(str(generated_dir / pattern)))
	seen: set[Path] = set()
	unique: list[Path] = []
	for path in paths:
		resolved = path.resolve()
		if resolved not in seen and path.exists() and path.stat().st_size > 0:
			seen.add(resolved)
			unique.append(path)
	return unique


def _score(stream: dict[str, Any]) -> tuple[float, int]:
	width = int(stream["width"])
	height = int(stream["height"])
	ratio_error = abs((width / height) - (16 / 9))
	pixels = width * height
	return (-ratio_error, pixels)


def select_assets(manifest_path: Path, generated_dir: Path, selected_dir: Path) -> dict[str, Any]:
	manifest = _read_json(manifest_path)
	selected_dir.mkdir(parents=True, exist_ok=True)
	selections: list[dict[str, Any]] = []
	missing: list[str] = []
	for shot in manifest["shots"]:
		beat = shot["beat"]
		candidates = []
		for path in _candidate_paths(generated_dir, beat):
			try:
				stream = _ffprobe_image(path)
			except Exception as exc:  # noqa: BLE001
				candidates.append({"path": str(path), "status": "reject", "reason": str(exc)})
				continue
			candidates.append({
				"path": str(path),
				"status": "candidate",
				"width": int(stream["width"]),
				"height": int(stream["height"]),
				"codec": stream.get("codec_name"),
				"sha256": _sha256(path),
				"score": _score(stream),
			})
		valid = [item for item in candidates if item["status"] == "candidate"]
		if not valid:
			missing.append(beat)
			selections.append({"beat": beat, "status": "missing", "candidates": candidates})
			continue
		best = sorted(valid, key=lambda item: item["score"], reverse=True)[0]
		source = Path(best["path"])
		target = selected_dir / f"shot_{beat}{source.suffix.lower()}"
		shutil.copy2(source, target)
		selections.append({
			"beat": beat,
			"status": "selected",
			"source": str(source),
			"selected_image": str(target),
			"width": best["width"],
			"height": best["height"],
			"sha256": _sha256(target),
			"candidates": candidates,
		})
	status = "PASS" if not missing else "MISSING_IMAGES"
	return {
		"schema_version": "article_ai_video_visuals.selected.v1",
		"status": status,
		"manifest": str(manifest_path),
		"generated_dir": str(generated_dir),
		"selected_dir": str(selected_dir),
		"missing_beats": missing,
		"selections": selections,
	}


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--manifest", required=True, type=Path)
	parser.add_argument("--generated-dir", required=True, type=Path)
	parser.add_argument("--selected-dir", required=True, type=Path)
	args = parser.parse_args()
	result = select_assets(args.manifest, args.generated_dir, args.selected_dir)
	out = args.project_dir / "ai_video_visuals" / "selected_visuals.json"
	_write_json(out, result)
	print(json.dumps({"status": result["status"], "selected_visuals": str(out), "missing_beats": result["missing_beats"]}, ensure_ascii=False, indent=2))
	if result["status"] != "PASS":
		raise SystemExit(2)


if __name__ == "__main__":
	main()
