import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Callable

from ..config import PROJECT_DIR, get_settings


PROMPT = """添付されたローカル画像ファイルを今すぐ読み取り、同じ植物を撮影した観察記録として植物の種類を推定してください。
返答は必ずJSONのみです。挨拶、説明、Markdown、コードフェンス、JSON外の文章は禁止です。

制約:
- JSONには必ず common_name_ja, scientific_name, confidence, candidates, visible_features, basic_profile_text, visual_appeal_text, care_notes, uncertainty_notes を含めてください。
- 断定できない場合は confidence を低くしてください。
- common_name_ja と scientific_name が不明な場合は null にしてください。
- candidates は最大3件、reason は各120字以内にしてください。
- candidates の confidence は0.0から1.0の小数で、候補全体の合計が1.0以下になるようにしてください。
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


def analyze_images(
    image_paths: list[Path],
    gemini_model: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
    identity_callback: Callable[[dict], None] | None = None,
) -> dict:
    total_started_at = time.perf_counter()
    settings = get_settings()
    model = clean_model_name(gemini_model) or clean_model_name(settings.gemini_model)
    if not settings.gemini_enabled:
        result = mock_result()
        if model:
            result["gemini_model"] = model
        result["analysis_timing"] = {
            "total_seconds": elapsed_seconds(total_started_at),
            "gemini_cli_seconds": 0.0,
            "mock": True,
        }
        return result

    with tempfile.TemporaryDirectory(prefix="plant-dex-gemini-") as temp_dir:
        copy_started_at = time.perf_counter()
        readable_paths = copy_images_for_gemini(image_paths, Path(temp_dir))
        copy_seconds = elapsed_seconds(copy_started_at)
        prompt = build_prompt(readable_paths)
        image_args = [f"@{path.absolute()}" for path in readable_paths]
        if progress_callback:
            progress_callback("identifying")
        cli_started_at = time.perf_counter()
        output = run_gemini_prompt(
            prompt,
            gemini_model=model,
            extra_args=[
                "--include-directories",
                str(Path(temp_dir)),
            ],
            trailing_args=image_args,
        )
        cli_seconds = elapsed_seconds(cli_started_at)

    try:
        parse_started_at = time.perf_counter()
        result = normalize_result(parse_json_output(output))
        parse_seconds = elapsed_seconds(parse_started_at)
    except JSONDecodeError as exc:
        preview = output[:1200] if output else "Gemini CLI returned empty output."
        raise RuntimeError(f"Gemini CLI output was not valid JSON: {exc}. Output: {preview}") from exc

    if model:
        result["gemini_model"] = model
    if identity_callback:
        identity_callback(dict(result))
    if progress_callback:
        progress_callback("writing_profile")
    profile_started_at = time.perf_counter()
    result = ensure_profile_texts(result, gemini_model=model)
    profile_seconds = elapsed_seconds(profile_started_at)
    result["analysis_timing"] = {
        "copy_images_seconds": copy_seconds,
        "gemini_cli_seconds": cli_seconds,
        "parse_seconds": parse_seconds,
        "profile_fill_seconds": profile_seconds,
        "total_seconds": elapsed_seconds(total_started_at),
        "image_count": len(image_paths),
        "model": model or "default",
    }
    return result


def elapsed_seconds(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)


def run_gemini_prompt(
    prompt: str,
    gemini_model: str | None = None,
    extra_args: list[str] | None = None,
    trailing_args: list[str] | None = None,
    use_yolo: bool = True,
) -> str:
    settings = get_settings()
    command_parts = shlex.split(settings.gemini_command, posix=os.name != "nt")
    if not use_yolo:
        command_parts = [part for part in command_parts if part not in {"--yolo", "-y"}]
    model = clean_model_name(gemini_model) or clean_model_name(settings.gemini_model)
    if model:
        command_parts = strip_model_args(command_parts)
    executable = shutil.which(command_parts[0]) or command_parts[0]
    command = [
        executable,
        *command_parts[1:],
        *(["--model", model] if model else []),
        *(extra_args or []),
        "--output-format",
        "text",
        "-p",
        prompt,
        *(trailing_args or []),
    ]
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        command = ["cmd", "/c", *command]

    process = subprocess.Popen(
        command,
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=settings.gemini_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        terminate_process_tree(process.pid)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        raise RuntimeError(
            f"Gemini CLI timed out after {settings.gemini_timeout_seconds} seconds."
        ) from exc

    if process.returncode != 0:
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        detail = stderr or stdout or "Gemini CLIの実行に失敗しました。"
        raise RuntimeError(f"Gemini CLI failed with code {process.returncode}: {detail}")
    if needs_gemini_auth(stdout, stderr):
        raise RuntimeError(
            "Gemini CLIがログイン確認で停止しました。PCのPowerShellで `gemini` を直接実行し、ブラウザ認証を完了してから再解析してください。"
        )
    return stdout or ""


def clean_model_name(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def strip_model_args(command_parts: list[str]) -> list[str]:
    cleaned: list[str] = []
    skip_next = False
    for part in command_parts:
        if skip_next:
            skip_next = False
            continue
        if part in {"--model", "-m"}:
            skip_next = True
            continue
        if part.startswith("--model="):
            continue
        cleaned.append(part)
    return cleaned


def terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return

    try:
        os.kill(pid, 9)
    except OSError:
        pass


def needs_gemini_auth(stdout: str | None, stderr: str | None) -> bool:
    text = f"{stdout or ''}\n{stderr or ''}".lower()
    markers = [
        "opening authentication page",
        "do you want to continue",
        "browser authentication",
    ]
    return any(marker in text for marker in markers)


def build_prompt(image_paths: list[Path]) -> str:
    return f"""{PROMPT}

上記添付された{len(image_paths)}枚の画像ファイルを読み取り、同一植物の観察として解析してください。
"""


def ensure_profile_texts(result: dict, gemini_model: str | None = None) -> dict:
    if result.get("basic_profile_text") and result.get("visual_appeal_text"):
        return result

    name = result.get("common_name_ja") or "不明な植物"
    scientific_name = result.get("scientific_name") or "不明"
    prompt = (
        f"{name}（{scientific_name}）について、JSONのみで返答してください: "
        '{"basic_profile_text":"120字以内の図鑑的特徴",'
        '"visual_appeal_text":"120字以内の見た目の魅力"}'
    )
    try:
        profile = normalize_result(
            parse_json_output(run_gemini_prompt(prompt, gemini_model=gemini_model, use_yolo=False))
        )
    except Exception:
        return result

    if not profile.get("basic_profile_text") and profile.get("description"):
        profile["basic_profile_text"] = truncate_text(str(profile["description"]), 120)
    if not result.get("basic_profile_text") and profile.get("basic_profile_text"):
        result["basic_profile_text"] = profile["basic_profile_text"]
    if not result.get("visual_appeal_text") and profile.get("visual_appeal_text"):
        result["visual_appeal_text"] = profile["visual_appeal_text"]
    return result



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
    result["confidence"] = normalize_confidence(result.get("confidence"))
    result["candidates"] = normalize_candidates(result.get("candidates"))
    if "ai_candidates" in result:
        result["ai_candidates"] = normalize_candidates(result.get("ai_candidates"))
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
        item["confidence"] = normalize_confidence(item.get("confidence"))
        normalized.append(item)
    normalize_candidate_confidence_sum(normalized)
    return normalized


def normalize_candidate_confidence_sum(candidates: list[dict]) -> None:
    total = sum(
        candidate["confidence"]
        for candidate in candidates
        if isinstance(candidate.get("confidence"), int | float)
    )
    if total <= 1:
        return

    for candidate in candidates:
        confidence = candidate.get("confidence")
        if isinstance(confidence, int | float):
            candidate["confidence"] = confidence / total


def normalize_confidence(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().rstrip("%")
        try:
            number = float(text)
        except ValueError:
            return 0.0
    else:
        return 0.0

    if number > 1:
        number = number / 100
    return max(0.0, min(number, 1.0))


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
