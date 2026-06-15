import os
import requests
from logger import log

VERCEL_TOKEN = os.getenv("VERCEL_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {VERCEL_TOKEN}",
}

def deploy_project(name, files):
    url = f"https://{name}.vercel.app"

    try:
        requests.post(
            "https://api.vercel.com/v13/deployments",
            json={
                "name": name,
                "files": files
            },
            headers=HEADERS
        )
    except Exception as e:
        log(str(e))

    return url


def delete_vercel_project(name):
    try:
        requests.delete(
            f"https://api.vercel.com/v9/projects/{name}",
            headers=HEADERS
        )
    except:
        pass