import os
import shutil

def delete_project_files(uid, name):
    path = f"projects/{uid}/{name}"
    if os.path.exists(path):
        shutil.rmtree(path)


def get_project_files(uid, name):
    base = f"projects/{uid}/{name}"
    files = []

    if not os.path.exists(base):
        return []

    for root, _, fs in os.walk(base):
        for f in fs:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base)

            with open(full, "r", encoding="utf-8") as x:
                files.append({"path": rel, "content": x.read()})

    return files