import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from ..config import PROJECT_DIR, get_settings


PROMPT = """あなたは庭木・草花の観察記録を整理する植物判定アシスタントです。
添付される3枚の写真は同じ植物を撮影したものです。
植物の種類を推定し、必ずJSONのみで返してください。

制約:
- 断定できない場合は confidence を低くしてください。
- common_name_ja と scientific_name が不明な場合は null にしてください。
- candidates は最大3件にしてください。
- Markdownや説明文をJSONの外に出さないでください。

JSONスキーマ:
{
  "common_name_ja": "標準和名またはnull",
  "scientific_name": "学名またはnull",
  "confidence": 0.0,
  "candidates": [
    {
      "common_name_ja": "候補名",
      "scientific_name": "候補学名またはnull",
      "confidence": 0.0,
      "reason": "候補理由"
    }
  ],
  "visible_features": ["見えている特徴"],
  "care_notes": "手入れや観察メモ",
  "uncertainty_notes": "不確実な点"
}
"""


def analyze_images(image_paths: list[Path]) -> dict:
    settings = get_settings()
    if not settings.gemini_enabled:
        return mock_result()

    prompt = build_prompt(image_paths)
    command_parts = shlex.split(settings.gemini_command, posix=os.name != "nt")
    executable = shutil.which(command_parts[0]) or command_parts[0]
    command = [
        executable,
        *command_parts[1:],
        "--output-format",
        "text",
        "-p",
        prompt,
    ]
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        command = ["cmd", "/c", *command]
    completed = subprocess.run(
        command,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=settings.gemini_timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Gemini CLIの実行に失敗しました。")

    return parse_json_output(completed.stdout)


def build_prompt(image_paths: list[Path]) -> str:
    image_list = "\n".join(f"- {path}" for path in image_paths)
    return f"""{PROMPT}

解析対象の画像ファイル:
{image_list}

上記3枚の画像ファイルを読み取り、同一植物の観察として解析してください。
"""


def parse_json_output(output: str) -> dict:
    text = output.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def mock_result() -> dict:
    return {
        "common_name_ja": "未解析サンプル",
        "scientific_name": None,
        "confidence": 0.1,
        "candidates": [
            {
                "common_name_ja": "未解析サンプル",
                "scientific_name": None,
                "confidence": 0.1,
                "reason": "PLANT_DEX_GEMINI_ENABLED=false のため、仮の結果を保存しました。",
            }
        ],
        "visible_features": [],
        "care_notes": "Gemini CLIを有効化すると実画像の解析結果に置き換えられます。",
        "uncertainty_notes": "これは動作確認用の仮データです。",
    }
