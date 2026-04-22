from datetime import datetime
from io import BytesIO
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import IMAGE_DIR

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 75 * 1024 * 1024
MIN_IMAGE_COUNT = 1
MAX_IMAGE_COUNT = 3
MAX_IMAGE_EDGE = 1280
JPEG_QUALITY = 78


async def save_observation_images(files: list[UploadFile]) -> tuple[str, list[Path]]:
    if not (MIN_IMAGE_COUNT <= len(files) <= MAX_IMAGE_COUNT):
        raise HTTPException(status_code=400, detail="画像は1枚から3枚まで送信できます。")

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

            try:
                optimized_content = optimize_image(content)
            except (OSError, UnidentifiedImageError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"画像ファイルとして読み取れません: {file.filename or index}",
                ) from exc

            output_path = observation_dir / f"{index}.jpg"
            output_path.write_bytes(optimized_content)
            saved_paths.append(output_path)
    except Exception:
        rmtree(observation_dir, ignore_errors=True)
        raise

    return observation_id, saved_paths


def optimize_image(content: bytes) -> bytes:
    with Image.open(BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)

        if image.mode in {"RGBA", "LA", "P"}:
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        output = BytesIO()
        image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        return output.getvalue()


def looks_like_supported_image(content: bytes, extension: str) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False
