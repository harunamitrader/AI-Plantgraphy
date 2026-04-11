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
- JSONには必ず common_name_ja, scientific_name, confidence, candidates, visible_features, basic_profile_text, visual_appeal_text, care_notes, uncertainty_notes を含めてください。
- 断定できない場合は confidence を低くしてください。
- common_name_ja と scientific_name が不明な場合は null にしてください。
- candidates は最大3件、reason は各120字以内にしてください。
- visible_features は最大5件、各25字以内にしてください。
- 画像ファイルを読み取れない場合も、JSONで uncertainty_notes に理由を書いてください。
- basic_profile_text は必須です。フィールドの説明ではなく、同定した植物そのものの図鑑文を書いてください。一般論だけで終わらせず、その植物固有の特徴を最低1つ含めてください。120字以内です。
- visual_appeal_text は必須です。フィールドの説明ではなく、同定した植物そのものの姿・雰囲気・観賞上の魅力を書いてください。120字以内です。
- できれば「推定した植物名をもとに」「記録した植物」「図鑑情報として整理できます」「再解析」など、欄の説明やシステム都合の文章は避けてください。
- care_notes と uncertainty_notes は、それぞれ120字以内にしてください。

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
  "basic_profile_text": "同定した植物そのものの図鑑文を120字以内で記述",
  "visual_appeal_text": "同定した植物そのものの姿・雰囲気・観賞上の魅力を120字以内で記述",
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
    basic_text = result.get("basic_profile_text")
    visual_text = result.get("visual_appeal_text")

    if not isinstance(basic_text, str) or not basic_text.strip():
        basic_text = result.get("plant_profile_text")

    if isinstance(basic_text, str) and basic_text.strip() and not is_placeholder_text(basic_text):
        result["basic_profile_text"] = truncate_text(basic_text.strip(), 120)
    else:
        result.pop("basic_profile_text", None)

    if isinstance(visual_text, str) and visual_text.strip() and not is_placeholder_text(visual_text):
        result["visual_appeal_text"] = truncate_text(visual_text.strip(), 120)
    else:
        result.pop("visual_appeal_text", None)

    legacy_profile = result.get("plant_profile")
    if isinstance(legacy_profile, dict):
        overview = legacy_profile.get("overview")
        if (
            "basic_profile_text" not in result
            and isinstance(overview, str)
            and overview.strip()
        ):
            result["basic_profile_text"] = truncate_text(overview.strip(), 120)

    name = result.get("common_name_ja") or "この植物"
    if "visual_appeal_text" not in result:
        result.pop("visual_appeal_text", None)
    result["care_notes"] = truncate_text(str(result.get("care_notes") or ""), 120)
    result["uncertainty_notes"] = truncate_text(str(result.get("uncertainty_notes") or ""), 120)
    result["visible_features"] = normalize_visible_features(result.get("visible_features"))
    result["candidates"] = normalize_candidates(result.get("candidates"))
    return result


def normalize_visible_features(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [truncate_text(str(feature).strip(), 25) for feature in value if str(feature).strip()][:5]


def normalize_candidates(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    normalized = []
    for candidate in value[:3]:
        if not isinstance(candidate, dict):
            continue
        item = dict(candidate)
        item["reason"] = truncate_text(str(item.get("reason") or ""), 120)
        normalized.append(item)
    return normalized


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("、。,. ") + "…"


def is_placeholder_text(text: str) -> bool:
    return "未生成です" in text


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
        "basic_profile_text": "Gemini CLIを有効化すると、解析された植物の基本的な特徴が入ります。",
        "visual_appeal_text": "Gemini CLIを有効化すると、解析された植物の見た目の特徴と魅力が入ります。",
        "care_notes": "Gemini CLIを有効化すると実画像の解析結果に置き換えられます。",
        "uncertainty_notes": "これは動作確認用の仮データです。",
    }
