import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def get_data_dir() -> Path:
    return Path(os.environ.get("PHANTOM_DATA", "./data"))


def ensure_dirs(data_dir: str | Path) -> None:
    data_dir = Path(data_dir)
    for subdir in ("prices", "rates", "notes"):
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)
