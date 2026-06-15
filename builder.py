import os
from logger import log

def build_project(data, user_id):
    base = f"projects/{user_id}/{data['projectName']}"
    os.makedirs(base, exist_ok=True)

    for f in data.get("files", []):
        path = os.path.join(base, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as file:
            file.write(f["content"])