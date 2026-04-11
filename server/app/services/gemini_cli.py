import json
import os
import shlex
import shutil
import subprocess
import tempfile
from json import JSONDecodeError
from pathlib import Path

from ..config import PROJECT_DIR, get_settings


PROMPT = """以下の3枚のローカル画像ファイルを今すぐ読み取り、同じ植物を撮影した観察記録として植物の種類を推定してください。
返答は必ずJSONのみです。挨拶、説明、Markdown、コードフェンス、JSON外の文章は禁止です。

制約:
- JSONには必ず common_name_ja, scientific_name, confidence, candidates, visible_features, plant_profile_text, care_notes, uncertainty_notes を含めてください。
- 断定できない場合は confidence を低くしてください。
- common_name_ja と scientific_name が不明な場合は null にしてください。
- candidates は最大3件にしてください。
- 画像ファイルを読み取れない場合も、JSONで uncertainty_notes に理由を書いてください。
- plant_profile_text は必須です。解析結果の植物について、基本的な特徴、見た目の特徴、魅力を自然な自由文で書いてください。80字以上260字以内です。

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
  "plant_profile_text": "この植物の基本的な特徴と見た目の特徴・魅力を最大260字で自由に記述",
  "care_notes": "手入れや観察メモ",
  "uncertainty_notes": "不確実な点"
}
"""


def analyze_images(image_paths: list[Path]) -> dict:
    settings = get_settings()
    if not settings.gemini_enabled:
        return mock_result()

    with tempfile.TemporaryDirectory(prefix="plant-dex-gemini-") as temp_dir:
        readable_paths = copy_images_for_gemini(image_paths, Path(temp_dir))
        prompt = build_prompt(readable_paths)
        command_parts = shlex.split(settings.gemini_command, posix=os.name != "nt")
        executable = shutil.which(command_parts[0]) or command_parts[0]
        
        # Add image attachments using the '@' prefix
        image_args = [f"@{path.absolute()}" for path in readable_paths]
        
        command = [
            executable,
            *command_parts[1:],
            "--include-directories",
            str(Path(temp_dir)),
            "--output-format",
            "text",
            "-p",
            prompt,
            *image_args,
        ]
        if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
            command = ["cmd", "/c", *command]
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.gemini_timeout_seconds,
            check=False,
        )
    if completed.returncode != 0:
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        detail = stderr or stdout or "Gemini CLIの実行に失敗しました。"
        raise RuntimeError(f"Gemini CLI failed with code {completed.returncode}: {detail}")

    try:
        return normalize_result(parse_json_output(completed.stdout or ""))
    except JSONDecodeError as exc:
        output = (completed.stdout or completed.stderr or "").strip()
        preview = output[:1200] if output else "Gemini CLI returned empty output."
        raise RuntimeError(f"Gemini CLI output was not valid JSON: {exc}. Output: {preview}") from exc


def build_prompt(image_paths: list[Path]) -> str:
    return f"""{PROMPT}

上記添付された3枚の画像ファイルを読み取り、同一植物の観察として解析してください。
"""



def copy_images_for_gemini(image_paths: list[Path], temp_dir: Path) -> list[Path]:
    copied_paths: list[Path] = []
    for index, source in enumerate(image_paths, start=1):
        suffix = source.suffix or ".jpg"
        target = temp_dir / f"plant-image-{index}{suffix}"
        shutil.copy2(source, target)
        copied_paths.append(target)
    return copied_paths


def parse_json_output(output: str) -> dict:
    text = output.strip()
    fenced = extract_fenced_json(text)
    if fenced:
        return json.loads(fenced)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        candidate = extract_first_json_object(text)
        if candidate is None:
            raise
        return json.loads(candidate)


def extract_fenced_json(text: str) -> str | None:
    marker = "```json"
    start = text.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = text.find("```", start)
    if end == -1:
        return None
    return text[start:end].strip()


def extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def normalize_result(result: dict) -> dict:
    profile_text = result.get("plant_profile_text")
    if isinstance(profile_text, str) and profile_text.strip():
        result["plant_profile_text"] = truncate_profile(profile_text.strip())
        return result

    legacy_profile = result.get("plant_profile")
    if isinstance(legacy_profile, dict):
        overview = legacy_profile.get("overview")
        if isinstance(overview, str) and overview.strip():
            result["plant_profile_text"] = truncate_profile(overview.strip())
            return result

    name = result.get("common_name_ja") or "この植物"
    features = result.get("visible_features") or []
    feature_text = "、".join(str(feature) for feature in features[:3])
    if feature_text:
        result["plant_profile_text"] = truncate_profile(
            f"{name}は、{feature_text}が印象的な植物です。"
            "基本的な特徴と見た目の魅力は、再解析や追加写真でさらに詳しく整理できます。"
        )
    else:
        result["plant_profile_text"] = truncate_profile(
            f"{name}は、写真から種類を推定した植物です。"
            "基本的な特徴や見た目の魅力は、花・葉・樹形が分かる写真を追加するとより詳しく整理できます。"
        )
    return result


def truncate_profile(text: str, limit: int = 260) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("、。,. ") + "…"


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
        "plant_profile_text": "Gemini CLIを有効化すると、解析された植物の基本特徴が入ります。",
        "care_notes": "Gemini CLIを有効化すると実画像の解析結果に置き換えられます。",
        "uncertainty_notes": "これは動作確認用の仮データです。",
    }
