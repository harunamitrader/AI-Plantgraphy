from pathlib import Path
from shutil import rmtree

from ..config import IMAGE_DIR


def remove_observation_images(image_path: str | None) -> None:
    if not image_path:
        return

    path = Path(image_path)
    try:
        observation_dir = path.parent.resolve()
        image_root = IMAGE_DIR.resolve()
        observation_dir.relative_to(image_root)
    except ValueError:
        return

    if observation_dir != image_root:
        rmtree(observation_dir, ignore_errors=True)
