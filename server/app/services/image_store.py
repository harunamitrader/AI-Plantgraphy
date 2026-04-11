from datetime import datetime
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from ..config import IMAGE_DIR

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 30 * 1024 * 1024


async def save_observation_images(files: list[UploadFile]) -> tuple[str, list[Path]]:
    if len(files) != 3:
        raise HTTPException(status_code=400, detail="画像は必ず3枚送信してください。")

    observation_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    observation_dir = IMAGE_DIR / observation_id
    observation_dir.mkdir(parents=True, exist_ok=False)

    saved_paths: list[Path] = []
    total_bytes = 0
    try:
        for index, file in enumerate(files, start=1):
            extension = Path(file.filename or "").suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"未対応の画像形式です: {extension or '拡張子なし'}")

            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="空の画像ファイルは保存できません。")
            if len(content) > MAX_FILE_BYTES:
                raise HTTPException(status_code=400, detail="画像サイズが大きすぎます。1枚10MB以内にしてください。")
            total_bytes += len(content)
            if total_bytes > MAX_TOTAL_BYTES:
                raise HTTPException(status_code=400, detail="画像の合計サイズが大きすぎます。合計30MB以内にしてください。")
            if not looks_like_supported_image(content, extension):
                raise HTTPException(status_code=400, detail=f"画像ファイルとして読み取れません: {file.filename or index}")

            output_path = observation_dir / f"{index}{extension}"
            output_path.write_bytes(content)
            saved_paths.append(output_path)
    except Exception:
        rmtree(observation_dir, ignore_errors=True)
        raise

    return observation_id, saved_paths


def looks_like_supported_image(content: bytes, extension: str) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False
