import os
import re
import json
import time
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class FileItem(BaseModel):
    path: str
    content: str


class ProjectResponse(BaseModel):
    projectName: str
    files: list[FileItem]


BASE_SYSTEM = "Return ONLY JSON"

BUILD_PROMPT = "Build app:\n{request}"
EDIT_PROMPT = "Edit:\n{edit_request}\n{current_code}"


def _clean(text):
    text = re.sub(r"```json", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def _call(prompt):
    res = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=BASE_SYSTEM + prompt
    )

    raw = _clean(res.text)
    return json.dumps(json.loads(raw), ensure_ascii=False)


def builder(req):
    return _call(BUILD_PROMPT.format(request=req))


def editor(req, current_code=""):
    return _call(EDIT_PROMPT.format(edit_request=req, current_code=current_code))