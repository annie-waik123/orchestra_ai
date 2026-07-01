import os
import json
import threading
from typing import Dict, Any, List

class JSONDatabase:
    """
    A thread-safe utility to manage JSON read/write operations.
    Acts as a lightweight document database for key-value stores.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._initialize_db()

    def _initialize_db(self):
        with self._lock:
            if not os.path.exists(self.file_path):
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=4)

    def read_all(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return {}

    def write_all(self, data: Dict[str, Any]):
        with self._lock:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

    def get(self, key: str) -> Any:
        data = self.read_all()
        return data.get(key)

    def set(self, key: str, value: Any):
        data = self.read_all()
        data[key] = value
        self.write_all(data)

    def delete(self, key: str):
        data = self.read_all()
        if key in data:
            del data[key]
            self.write_all(data)
