from datetime import datetime, timezone
from pathlib import Path


def save_screenshot(image_bytes: bytes, output_dir: Path, slug: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    file_path = output_dir / f"{slug}-{timestamp}.png"
    file_path.write_bytes(image_bytes)
    return file_path
