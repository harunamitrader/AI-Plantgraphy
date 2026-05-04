import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Callable

from ..config import PROJECT_DIR, get_settings


PLANT_IDENTIFIER_SKILL_DIR = PROJECT_DIR / "skills" / "plant-json-identifier"
PLANT_IDENTIFIER_CONTRACT_PATH = PLANT_IDENTIFIER_SKILL_DIR / "references" / "output-contract.md"
DEFAULT_IDENTIFIER_SCHEMA = '{"common_name_ja":null,"scientific_name":null,"confidence":0.0,"candidates":[],"visible_features":[],"uncertainty_notes":""}'


PROFILE_PROMPT = """植物名から図鑑用の短い解説をJSON 1個だけで返してください。
JSON以外の文章、説明、Markdown、コードフェンスは禁止です。

必須JSON:
{"basic_profile_text":"","visual_appeal_text":"","care_notes":""}

ルール:
- 3項目とも必須。null禁止、空文字禁止
- 各項目は120字以内
- basic_profile_text はその植物の基本特徴
- visual_appeal_text は見た目や観賞上の魅力
- care_notes は一般的な育て方や管理の要点
"""


def build_identifier_prompt() -> str:
    contract = load_identifier_contract()
    required_json = contract["required_json"] or DEFAULT_IDENTIFIER_SCHEMA
    lines = [
        "画像だけを見て、同じ植物の観察結果をJSON 1個だけで返してください。",
        "JSON以外の文章、説明、Markdown、コードフェンスは禁止です。",
        "",
        "必須JSON:",
        required_json,
        "",
        "ルール:",
        "- common_name_ja を使う",
        "- scientific_name が不明なら null",
        "- confidence は 0.0 から 1.0",
        "- candidates は最大3件",
        "- visible_features は最大5件",
        "- 画像を読めない場合も uncertainty_notes に短く書く",
    ]
    for item in contract["forbidden_keys"]:
        lines.append(f"- {item} は使わない")
    return "\n".join(lines)


def load_identifier_contract() -> dict:
    text = read_text_if_exists(PLANT_IDENTIFIER_CONTRACT_PATH)
    if not text:
        return {
            "required_json": DEFAULT_IDENTIFIER_SCHEMA,
            "required_keys": list(json.loads(DEFAULT_IDENTIFIER_SCHEMA).keys()),
            "forbidden_keys": ["common_name", "plant_name"],
        }

    required_json = extract_json_code_fence(text) or DEFAULT_IDENTIFIER_SCHEMA
    forbidden_keys = extract_forbidden_top_level_keys(text)
    normalized_json = normalize_contract_json(required_json)
    return {
        "required_json": normalized_json,
        "required_keys": list(json.loads(normalized_json).keys()),
        "forbidden_keys": forbidden_keys,
    }


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def normalize_contract_json(text: str) -> str:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return DEFAULT_IDENTIFIER_SCHEMA
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def extract_json_code_fence(text: str) -> str | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def extract_forbidden_top_level_keys(text: str) -> list[str]:
    match = re.search(r"alternate top-level keys such as (.+)", text)
    if not match:
        return ["common_name", "plant_name"]
    segment = match.group(1).strip().rstrip(".")
    keys = []
    for item in segment.split(","):
        cleaned = item.strip(" `")
        if cleaned.startswith("or "):
            cleaned = cleaned[3:].strip(" `")
        if cleaned:
            keys.append(cleaned)
    return keys


PROMPT = build_identifier_prompt()


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

    with tempfile.TemporaryDirectory(prefix="ai-plantgraphy-gemini-") as temp_dir:
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
            output_format="json",
        )
        cli_seconds = elapsed_seconds(cli_started_at)
        parse_started_at = time.perf_counter()
        try:
            parsed = parse_json_output(output)
            violations = validate_identifier_payload(parsed)
            if violations:
                retry_output = run_gemini_prompt(
                    build_identifier_retry_prompt(violations),
                    gemini_model=model,
                    extra_args=[
                        "--include-directories",
                        str(Path(temp_dir)),
                    ],
                    trailing_args=image_args,
                    output_format="json",
                )
                retry_parsed = parse_json_output(retry_output)
                retry_violations = validate_identifier_payload(retry_parsed)
                if not retry_violations:
                    output = retry_output
                    parsed = retry_parsed
            result = normalize_result(parsed)
            parse_seconds = elapsed_seconds(parse_started_at)
        except JSONDecodeError as exc:
            try:
                result = normalize_result(
                    parse_json_output(coerce_analysis_output_to_json(output, gemini_model=model))
                )
                parse_seconds = elapsed_seconds(parse_started_at)
            except JSONDecodeError:
                heuristic = normalize_result(parse_plaintext_analysis_output(output))
                if heuristic.get("common_name_ja") or heuristic.get("scientific_name"):
                    result = heuristic
                    parse_seconds = elapsed_seconds(parse_started_at)
                else:
                    preview = output[:1200] if output else "Gemini CLI returned empty output."
                    raise RuntimeError(f"Gemini CLI output was not valid JSON: {exc}. Output: {preview}") from exc

    if model:
        result["gemini_model"] = model
    if identity_callback:
        identity_callback(dict(result))
    result["analysis_timing"] = {
        "copy_images_seconds": copy_seconds,
        "gemini_cli_seconds": cli_seconds,
        "parse_seconds": parse_seconds,
        "profile_fill_seconds": 0.0,
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
    output_format: str = "text",
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
        output_format,
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
    return extract_gemini_response(stdout or "", output_format=output_format)


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


def build_identifier_retry_prompt(violations: list[str]) -> str:
    violation_text = " / ".join(violations[:6])
    return (
        f"{PROMPT}\n\n"
        "重要:\n"
        "- 前回の返答はスキーマ違反でした。最初からやり直してください。\n"
        "- トップレベルキーは common_name_ja, scientific_name, confidence, candidates, visible_features, uncertainty_notes だけです。\n"
        f"- 修正する違反: {violation_text}"
    )


def validate_identifier_payload(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["top-level JSON object required"]

    contract = load_identifier_contract()
    required_keys = set(contract.get("required_keys") or [])
    forbidden_keys = set(contract.get("forbidden_keys") or [])
    actual_keys = set(payload.keys())

    violations: list[str] = []
    missing_keys = [key for key in required_keys if key not in actual_keys]
    extra_keys = [key for key in payload.keys() if key not in required_keys]
    forbidden_present = [key for key in payload.keys() if key in forbidden_keys]

    if missing_keys:
        violations.append(f"missing keys: {', '.join(missing_keys)}")
    if extra_keys:
        violations.append(f"extra keys: {', '.join(extra_keys)}")
    if forbidden_present:
        violations.append(f"forbidden keys: {', '.join(forbidden_present)}")
    return violations


def extract_gemini_response(output: str, output_format: str = "text") -> str:
    if output_format != "json":
        return output

    candidate = extract_first_json_object(output.strip())
    if candidate is None:
        return output

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return output

    if isinstance(payload, dict) and isinstance(payload.get("response"), str):
        return payload["response"]
    return output


def coerce_analysis_output_to_json(output: str, gemini_model: str | None = None) -> str:
    prompt = f"""次の自由文を、書いてある内容だけでJSON 1個に変換してください。
推測で補わないでください。JSON以外の文章は禁止です。

必須JSON:
{{"common_name_ja":null,"scientific_name":null,"confidence":0.0,"candidates":[],"visible_features":[],"uncertainty_notes":""}}

ルール:
- common_name_ja と scientific_name が不明なら null
- confidence は 0.0 から 1.0
- candidates は最大3件
- visible_features は最大5件

自由文:
{output[:4000]}
"""
    return run_gemini_prompt(
        prompt,
        gemini_model=gemini_model,
        use_yolo=False,
        output_format="json",
    )


def parse_plaintext_analysis_output(output: str) -> dict:
    text = str(output or "").strip()
    common_name, scientific_name = extract_names_from_plaintext(text)
    visible_features = extract_visible_features_from_plaintext(text)
    confidence = infer_confidence_from_plaintext(text, common_name, scientific_name)
    uncertainty = "Gemini CLIが自由文で返答したため本文から抽出しました。"
    reason = "Gemini CLIの自由文応答に最有力候補として記載されていました。"

    candidates = []
    if common_name or scientific_name:
        candidates.append(
            {
                "common_name_ja": common_name,
                "scientific_name": scientific_name,
                "confidence": confidence,
                "reason": reason,
            }
        )

    return {
        "common_name_ja": common_name,
        "scientific_name": scientific_name,
        "confidence": confidence,
        "candidates": candidates,
        "visible_features": visible_features,
        "uncertainty_notes": uncertainty,
    }


def extract_names_from_plaintext(text: str) -> tuple[str | None, str | None]:
    scientific_match = re.search(r"学名[:：]?\s*\*?([A-Z][A-Za-z0-9 ._-]+)\*?", text)
    scientific_name = scientific_match.group(1).strip() if scientific_match else None

    common_name = None
    bold_match = re.search(r"\*\*([^*（）\n]+?)(?:（[^）]+）)?\*\*", text)
    if bold_match:
        common_name = bold_match.group(1).strip()

    if not common_name:
        line_match = re.search(r"この植物は\s+([^\n。]+?)\s+であると推定", text)
        if line_match:
            common_name = line_match.group(1).strip(" 　*")

    if common_name and "学名" in common_name:
        common_name = common_name.split("学名", 1)[0].strip(" ：:（(")
    return common_name or None, scientific_name


def extract_visible_features_from_plaintext(text: str) -> list[str]:
    features: list[str] = []
    patterns = [
        r"\*\*[^*]+特徴[^*]*\*\*[:：]\s*([^\n]+)",
        r"\*\*[^*]+形態[^*]*\*\*[:：]\s*([^\n]+)",
        r"\*\*[^*]+葉[^*]*\*\*[:：]\s*([^\n]+)",
        r"\*\*[^*]+花[^*]*\*\*[:：]\s*([^\n]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group(1).strip(" *")
            if value:
                features.append(value)
    return normalize_visible_features(features)


def infer_confidence_from_plaintext(
    text: str,
    common_name_ja: str | None,
    scientific_name: str | None,
) -> float:
    lowered = text.lower()
    if "非常に高い" in text:
        return 0.95
    if "高いです" in text or "高いと" in text:
        return 0.9
    if "推定されます" in text and (common_name_ja or scientific_name):
        return 0.8
    if "candidate" in lowered and (common_name_ja or scientific_name):
        return 0.7
    return 0.0


def generate_plant_profile(
    common_name_ja: str | None,
    scientific_name: str | None,
    gemini_model: str | None = None,
) -> dict:
    name = common_name_ja or scientific_name or "名称未確定の植物"
    scientific = scientific_name or "学名未確定"
    prompt = f"""{PROFILE_PROMPT}

対象植物:
- 植物名: {name}
- 学名: {scientific}
"""
    profile = normalize_result(
        parse_json_output(
            run_gemini_prompt(
                prompt,
                gemini_model=gemini_model,
                use_yolo=False,
                output_format="json",
            )
        )
    )
    profile = ensure_profile_texts(
        {
            **profile,
            "common_name_ja": common_name_ja,
            "scientific_name": scientific_name,
        },
        gemini_model=gemini_model,
    )
    return {
        "basic_profile_text": profile.get("basic_profile_text"),
        "visual_appeal_text": profile.get("visual_appeal_text"),
        "care_notes": profile.get("care_notes"),
    }


def ensure_profile_texts(result: dict, gemini_model: str | None = None) -> dict:
    if result.get("basic_profile_text") and result.get("visual_appeal_text"):
        return result

    name = result.get("common_name_ja") or "不明な植物"
    scientific_name = result.get("scientific_name") or "不明"
    prompt = (
        f"対象植物は {name}（{scientific_name}）です。別の植物の説明は禁止です。"
        "植物の再同定はせず、この植物についてだけ書いてください。"
        "返答はJSONのみで、basic_profile_text と visual_appeal_text の両方を必ず120字以内の文字列で返してください。"
        '{"basic_profile_text":"この植物の基本的な特徴","visual_appeal_text":"この植物の見た目の特徴と魅力"}'
    )
    try:
        profile = normalize_result(
            parse_json_output(
                run_gemini_prompt(
                    prompt,
                    gemini_model=gemini_model,
                    use_yolo=False,
                    output_format="json",
                )
            )
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
    result = apply_result_aliases(dict(result))
    result = apply_structured_field_fallbacks(result)
    result = promote_top_candidate(result)
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

    care_text = str(result.get("care_notes") or "").strip()
    if care_text and not is_placeholder_text(care_text):
        result["care_notes"] = truncate_text(care_text, 120)
    else:
        result["care_notes"] = ""
    result["visible_features"] = normalize_visible_features(result.get("visible_features"))
    result["confidence"] = normalize_confidence(result.get("confidence"))
    result["candidates"] = normalize_candidates(result.get("candidates"))
    result["uncertainty_notes"] = truncate_text(
        build_uncertainty_notes(result, str(result.get("uncertainty_notes") or "").strip()),
        120,
    )
    if "ai_candidates" in result:
        result["ai_candidates"] = normalize_candidates(result.get("ai_candidates"))
    return result


def apply_result_aliases(result: dict) -> dict:
    identification = result.get("plant_identification")
    identification = identification if isinstance(identification, dict) else {}
    common_name = clean_optional_text(result.get("common_name_ja")) or (
            clean_optional_text(result.get("common_name"))
            or clean_optional_text(result.get("plant_name"))
            or clean_optional_text(result.get("name"))
            or clean_optional_text(identification.get("common_name"))
            or clean_optional_text(identification.get("common_name_ja"))
            or clean_optional_text(identification.get("name"))
    )
    scientific_name = clean_optional_text(result.get("scientific_name")) or (
            clean_optional_text(result.get("scientificName"))
            or clean_optional_text(result.get("latin_name"))
            or clean_optional_text(result.get("botanical_name"))
            or clean_optional_text(identification.get("scientific_name"))
            or clean_optional_text(identification.get("scientificName"))
            or clean_optional_text(identification.get("botanical_name"))
    )
    split_name, split_scientific = split_combined_name(common_name)
    result["common_name_ja"] = split_name
    result["scientific_name"] = scientific_name or split_scientific
    return result


def apply_structured_field_fallbacks(result: dict) -> dict:
    if not clean_optional_text(result.get("care_notes")):
        result["care_notes"] = clean_optional_text(result.get("care_advice")) or ""

    if not clean_optional_text(result.get("basic_profile_text")):
        result["basic_profile_text"] = build_basic_profile_from_result(result)

    if not clean_optional_text(result.get("visual_appeal_text")):
        result["visual_appeal_text"] = build_visual_profile_from_result(result)

    if not isinstance(result.get("visible_features"), list) or not result.get("visible_features"):
        result["visible_features"] = extract_visible_features_from_result(result)

    if not isinstance(result.get("candidates"), list) or not result.get("candidates"):
        candidate = build_primary_candidate(result)
        if candidate:
            result["candidates"] = [candidate]

    if normalize_confidence(result.get("confidence")) == 0.0:
        result["confidence"] = infer_confidence_from_result(result)

    return result


def promote_top_candidate(result: dict) -> dict:
    candidates = result.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return result

    top = candidates[0] if isinstance(candidates[0], dict) else None
    if not top:
        return result

    current_name = clean_optional_text(result.get("common_name_ja"))
    current_scientific = clean_optional_text(result.get("scientific_name"))
    current_confidence = normalize_confidence(result.get("confidence"))
    top_name = clean_optional_text(top.get("common_name_ja")) or clean_optional_text(top.get("name"))
    top_scientific = clean_optional_text(top.get("scientific_name"))
    top_confidence = normalize_confidence(top.get("confidence"))

    if not current_name and top_name:
        result["common_name_ja"] = top_name
    if not current_scientific and top_scientific:
        result["scientific_name"] = top_scientific
    if current_confidence == 0.0 and top_confidence > 0.0:
        result["confidence"] = top_confidence

    if current_name and top_name and current_name == top_name and current_scientific != top_scientific and top_scientific:
        result["scientific_name"] = top_scientific
        if top_confidence > current_confidence:
            result["confidence"] = top_confidence
    return result


def clean_optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def split_combined_name(value: str | None) -> tuple[str | None, str | None]:
    text = clean_optional_text(value)
    if not text:
        return None, None

    match = re.match(r"^(.*?)\s*[\(（]\s*([A-Z][A-Za-z0-9 ._-]+)\s*[\)）]\s*$", text)
    if not match:
        return text, None

    common_name = clean_optional_text(match.group(1))
    scientific_name = clean_optional_text(match.group(2))
    return common_name or text, scientific_name


def build_basic_profile_from_result(result: dict) -> str | None:
    summary = clean_optional_text(result.get("observation_summary"))
    if summary:
        return truncate_text(summary, 120)

    observation_details = get_observation_details(result)
    observations = result.get("observations")
    if isinstance(observations, list):
        for item in observations:
            if not isinstance(item, dict):
                continue
            part = clean_optional_text(item.get("part"))
            description = clean_optional_text(item.get("description"))
            if part and description and part in {"全体", "株姿", "草姿"}:
                return truncate_text(description, 120)
            if description:
                return truncate_text(description, 120)

    characteristics = get_characteristics(result)
    if isinstance(characteristics, dict) and characteristics:
        parts = []
        for key in ["growth_form", "leaf_shape", "flower_color"]:
            value = clean_optional_text(characteristics.get(key))
            if value:
                parts.append(value)
        if parts:
            return truncate_text("、".join(parts), 120)

    nested_characteristics = observation_details.get("characteristics")
    if isinstance(nested_characteristics, list) and nested_characteristics:
        return truncate_text(str(nested_characteristics[0]).strip(), 120)
    return None


def build_visual_profile_from_result(result: dict) -> str | None:
    observations = result.get("observations")
    if isinstance(observations, list):
        descriptions = []
        for item in observations:
            if not isinstance(item, dict):
                continue
            description = clean_optional_text(item.get("description"))
            if description:
                descriptions.append(description)
        if descriptions:
            return truncate_text(" ".join(descriptions[:2]), 120)

    summary = clean_optional_text(result.get("observation_summary"))
    if summary:
        return truncate_text(summary, 120)

    observation_details = get_observation_details(result)
    nested_characteristics = observation_details.get("characteristics")
    if isinstance(nested_characteristics, list) and nested_characteristics:
        return truncate_text(" ".join(str(item).strip() for item in nested_characteristics[:2] if str(item).strip()), 120)
    return None


def extract_visible_features_from_result(result: dict) -> list[str]:
    features: list[str] = []
    characteristics = get_characteristics(result)
    if isinstance(characteristics, dict):
        for key in ["flower_color", "flower_type", "leaf_pattern", "leaf_shape", "flower_structure", "leaves", "growth_habit"]:
            value = clean_optional_text(characteristics.get(key))
            if value:
                features.append(value)

    observations = result.get("observations")
    if isinstance(observations, list):
        for item in observations:
            if not isinstance(item, dict):
                continue
            description = clean_optional_text(item.get("description"))
            if description:
                features.append(description)

    observation_details = get_observation_details(result)
    nested_characteristics = observation_details.get("characteristics")
    if isinstance(nested_characteristics, list):
        for item in nested_characteristics:
            value = clean_optional_text(item)
            if value:
                features.append(value)
    return normalize_visible_features(features)


def build_primary_candidate(result: dict) -> dict | None:
    common_name = clean_optional_text(result.get("common_name_ja"))
    scientific_name = clean_optional_text(result.get("scientific_name"))
    if not (common_name or scientific_name):
        return None
    confidence = infer_confidence_from_result(result)
    return {
        "common_name_ja": common_name,
        "scientific_name": scientific_name,
        "confidence": confidence,
        "reason": "構造化された解析結果で植物名が明示されていました。",
    }


def infer_confidence_from_result(result: dict) -> float:
    common_name = clean_optional_text(result.get("common_name_ja"))
    scientific_name = clean_optional_text(result.get("scientific_name"))
    if not (common_name or scientific_name):
        return 0.0

    observations = result.get("observations")
    characteristics = get_characteristics(result)
    summary = clean_optional_text(result.get("observation_summary"))
    observation_details = get_observation_details(result)
    nested_characteristics = observation_details.get("characteristics")

    if common_name and scientific_name and isinstance(observations, list) and observations:
        return 0.82
    if common_name and scientific_name and isinstance(characteristics, dict) and characteristics:
        return 0.78
    if common_name and scientific_name and isinstance(nested_characteristics, list) and nested_characteristics:
        return 0.78
    if common_name and scientific_name and summary:
        return 0.75
    if common_name or scientific_name:
        return 0.68
    return 0.0


def build_uncertainty_notes(result: dict, current_note: str) -> str:
    if current_note:
        return current_note

    confidence = normalize_confidence(result.get("confidence"))
    candidates = result.get("candidates")
    candidate_count = len(candidates) if isinstance(candidates, list) else 0
    scientific_name = clean_optional_text(result.get("scientific_name"))

    notes: list[str] = []
    if confidence < 0.75:
        notes.append("同定の確度はまだ高くありません。")
    if candidate_count <= 1 and confidence < 0.75:
        notes.append("他候補は十分に絞り込めませんでした。")
    if not scientific_name and confidence < 0.85:
        notes.append("学名は未確定です。")

    return truncate_text("".join(notes), 120) or ""


def get_observation_details(result: dict) -> dict:
    value = result.get("observation_details")
    return value if isinstance(value, dict) else {}


def get_characteristics(result: dict) -> dict:
    value = result.get("characteristics")
    if isinstance(value, dict):
        return value
    observation_details = get_observation_details(result)
    nested = observation_details.get("characteristics")
    return nested if isinstance(nested, dict) else {}


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
    normalized = str(text or "").strip()
    if not normalized:
        return True
    placeholders = {
        "基本的な特徴",
        "見た目の特徴と魅力",
        "手入れメモ",
        "基本情報",
        "見た目情報",
        "特徴",
        "魅力",
        "説明",
        "プロフィール",
    }
    if normalized in placeholders:
        return True
    return "未生成です" in normalized


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
        "uncertainty_notes": "これは動作確認用の仮データです。",
    }
