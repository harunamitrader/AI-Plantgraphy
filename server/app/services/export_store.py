import json
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ..config import DB_PATH, EXPORT_DIR, IMAGE_DIR


def create_export_zip() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = EXPORT_DIR / f"ai-plantgraphy-export-{export_id}.zip"

    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        if DB_PATH.exists():
            archive.write(DB_PATH, "plants.sqlite")

        if IMAGE_DIR.exists():
            for path in IMAGE_DIR.rglob("*"):
                if path.is_file():
                    archive.write(path, Path("images") / path.relative_to(IMAGE_DIR))

        manifest = {
            "created_at": datetime.now().isoformat(),
            "database": "plants.sqlite",
            "images": "images/",
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return output_path
