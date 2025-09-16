from pathlib import Path

class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, key: str, data: bytes) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get_path(self, key: str) -> Path:
        return self.root / key
