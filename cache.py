import json
import pathlib
import hashlib

class Cache:
    def __init__(self, directory="data/raw"):
        self.directory = pathlib.Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
    
    def _key_to_path(self, key):
        filename = hashlib.md5(key.encode()).hexdigest() + ".json"
        return self.directory / filename

    def get(self, key):
        path = self._key_to_path(key)
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return None 

    def set(self, key, value):
        path = self._key_to_path(key)
        with open(path, "w") as f:
            json.dump(value, f)