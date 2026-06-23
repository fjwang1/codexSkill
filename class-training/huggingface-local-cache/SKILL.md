---
name: huggingface-local-cache
description: Use when working with Hugging Face / HF Hub models or datasets on this machine, especially authenticated downloads, gated repos, large model caches, dataset samples, snapshot_download, hf_hub_download, or avoiding internal-disk cache bloat. Keeps HF token handling local and routes caches/artifacts to /Volumes/GT34.
---

# Hugging Face Local Cache

Use this skill whenever a task downloads or inspects Hugging Face models, datasets, Spaces assets, or gated/public repos.

## Local Defaults

- Store Hugging Face auth and cache under `/Volumes/GT34/Caches/huggingface`.
- Store reusable model snapshots under `/Volumes/GT34/AI`.
- Store downloaded source archives or dataset material under `/Volumes/GT34/Downloads`.
- Store generated task outputs under `/Volumes/GT34/Generated`.
- Before disk-heavy work, verify `/Volumes/GT34` is mounted and writable.

Always set these environment variables for HF work:

```bash
export HF_HOME=/Volumes/GT34/Caches/huggingface
export HF_HUB_CACHE=/Volumes/GT34/Caches/huggingface/hub
export HF_DATASETS_CACHE=/Volumes/GT34/Caches/huggingface/datasets
```

If the current Python environment lacks `huggingface_hub`, prefer:

```bash
/Users/wangfangjia/code/qwen3-tts-apple-silicon-test/.venv/bin/python
```

## Token Handling

- A local HF token is expected at `/Volumes/GT34/Caches/huggingface/token`.
- Never print, paste, commit, copy into a skill, or include the token in final answers.
- Keep the token file mode at `600` and the HF cache directory mode at `700`.
- Do not use `--add-to-git-credential` unless the user explicitly asks.
- For this machine, a read-only token is sufficient for downloading public, private, or accepted gated repos. Write and inference endpoint permissions are not needed for normal local downloads.

Verify auth without exposing secrets:

```bash
HF_HOME=/Volumes/GT34/Caches/huggingface \
/Users/wangfangjia/code/qwen3-tts-apple-silicon-test/.venv/bin/python - <<'PY'
from huggingface_hub import whoami
print(whoami().get("name", "auth ok"))
PY
```

## Download Patterns

Inspect before downloading:

```python
from huggingface_hub import list_repo_files

files = list_repo_files("owner/repo", repo_type="model")  # or repo_type="dataset"
for path in files[:50]:
	print(path)
```

Download one file:

```python
from huggingface_hub import hf_hub_download

path = hf_hub_download(
	repo_id="owner/repo",
	filename="path/in/repo/file.wav",
	repo_type="dataset",
	local_dir="/Volumes/GT34/Downloads/owner-repo-samples",
)
print(path)
```

Download a filtered snapshot:

```python
from huggingface_hub import snapshot_download

path = snapshot_download(
	repo_id="owner/repo",
	repo_type="model",
	local_dir="/Volumes/GT34/AI/owner-repo",
	allow_patterns=["*.json", "*.safetensors", "tokenizer.*"],
	ignore_patterns=["*.bin", "*.onnx", "*.msgpack"],
)
print(path)
```

For large datasets, prefer `list_repo_files` plus targeted `hf_hub_download` instead of `snapshot_download` for the whole repo.

## Gated Repo Diagnosis

- `401`: token is missing/invalid or `HF_HOME` was not set for that command.
- `403`: token is valid but the user likely has not accepted the gated repo terms, or the token lacks access to that private/gated repo.
- `404`: repo id, repo type, branch, or filename is likely wrong.

When a gated model/dataset fails, ask the user to open the repo page in their browser and accept the license/access terms, then rerun with the same `HF_HOME`.

## Operational Rules

- Keep large files off `/Users/wangfangjia` unless a repo explicitly requires them.
- Prefer `allow_patterns` and `ignore_patterns` for models with many formats.
- Prefer individual sample files for voice-prompt scouting instead of full corpus downloads.
- Keep manifests with source repo id, license, downloaded filenames, output paths, and any transformation applied.
- Do not infer speaker identities from public speech datasets; use dataset speaker IDs only.
