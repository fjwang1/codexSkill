#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${MLX_WHISPER_PYTHON:-}" ]]; then
	PYTHON_CANDIDATES=("$MLX_WHISPER_PYTHON")
else
	PYTHON_CANDIDATES=(
		"/Users/wangfangjia/code/bilibili-mcp/.venv-asr/bin/python"
		"$SCRIPT_DIR/../.venv/bin/python"
		"python3.13"
		"python3"
	)
fi

for candidate in "${PYTHON_CANDIDATES[@]}"; do
	if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
		if "$candidate" - <<'PY' >/dev/null 2>&1
import mlx_whisper
PY
		then
			exec "$candidate" "$SCRIPT_DIR/transcribe_bilibili_video.py" "$@"
		fi
	fi
done

cat >&2 <<'EOF'
Could not find a Python environment with mlx_whisper installed.

Install one with:
  python3.13 -m venv /Users/wangfangjia/code/bilibili-mcp/.venv-asr
  /Users/wangfangjia/code/bilibili-mcp/.venv-asr/bin/pip install mlx-whisper

Or set:
  MLX_WHISPER_PYTHON=/path/to/python
EOF
exit 1
