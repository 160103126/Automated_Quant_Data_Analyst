from pathlib import Path


def load_skill(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Runtime skill not found: {path}")
    return path.read_text(encoding="utf-8")
