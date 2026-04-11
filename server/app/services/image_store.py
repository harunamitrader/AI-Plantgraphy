from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from ..config import IMAGE_DIR

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_BYTES = 10 * 1024 * 1024


async def save_observation_images(files: list[UploadFile]) -> tuple[str, list[Path]]:
    if len(files) != 3:
        raise HTTPException(status_code=400, detail="画像は必ず3枚送信してください。")

    observation_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    observation_dir = IMAGE_DIR / observation_id
    observation_dir.mkdir(parents=True, exist_ok=False)

    saved_paths: list[Path] = []
    for index, file in enumerate(files, start=1):
        extension = Path(file.filename or "").suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"未対応の画像形式です: {extension}")

        content = await file.read()
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="画像サイズが大きすぎます。")

        output_path = observation_dir / f"{index}{extension}"
        output_path.write_bytes(content)
        saved_paths.append(output_path)

    return observation_id, saved_paths

