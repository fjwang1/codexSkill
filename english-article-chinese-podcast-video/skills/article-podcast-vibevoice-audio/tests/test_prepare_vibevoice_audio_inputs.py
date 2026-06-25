from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_vibevoice_audio_inputs.py"


def test_prepare_inputs_can_preserve_worldview_four_speaker_tags_when_min_turns_disabled(tmp_path: Path) -> None:
	project_dir = tmp_path / "project"
	project_dir.mkdir()
	(project_dir / "podcast_script.md").write_text(
		"\n".join([
			"# 测试稿",
			"",
			"## 正文",
			"",
			"Speaker 0: 第一位说话人提到 2026 年的背景。",
			"Speaker 2: 第三位说话人补充 14% 的变化。",
			"Speaker 3: 第四位说话人回应 AI 和 GDP 的影响。",
		])
		+ "\n",
		encoding="utf-8",
	)

	result = subprocess.run(
		[
			sys.executable,
			str(SCRIPT),
			"--project-dir",
			str(project_dir),
			"--min-speaker-turns",
			"0",
		],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)

	output = json.loads(result.stdout)
	assert output["speaker_counts"] == {
		"Speaker 0": 1,
		"Speaker 1": 0,
		"Speaker 2": 1,
		"Speaker 3": 1,
	}
	vibevoice_input = (project_dir / "audio/vibevoice_dialogue.txt").read_text(encoding="utf-8")
	assert "Speaker 2: 第三位说话人补充百分之十四的变化。" in vibevoice_input
	assert "Speaker 3: 第四位说话人回应 A I 和 G D P 的影响。" in vibevoice_input
	manifest = json.loads((project_dir / "audio/audio_manifest.json").read_text(encoding="utf-8"))
	assert manifest["speaker_counts"] == output["speaker_counts"]
	assert [turn["speaker"] for turn in manifest["turns"]] == ["Speaker 0", "Speaker 2", "Speaker 3"]
