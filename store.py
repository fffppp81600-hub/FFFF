import json
import os

FILE = "data.json"

def load():
    if not os.path.exists(FILE):
        return {}
    return json.load(open(FILE))

def save(d):
    json.dump(d, open(FILE, "w"))

def add_project(uid, name, url):
    d = load()
    d.setdefault(uid, [])
    d[uid].append({"name": name, "url": url})
    save(d)

def get_projects(uid):
    return load().get(uid, [])