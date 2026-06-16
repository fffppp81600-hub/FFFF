import json
import re

def safe_parse(text):
    if not text:
        return None
    try:
        # نظف أي markdown
        text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        # استخرج أول { ... }
        start = text.find("{")
        end   = text.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(text[start:end+1])
        # تحقق من الهيكل
        if "projectName" not in data or "files" not in data:
            return None
        paths = {f.get("path") for f in data["files"]}
        if not {"index.html","style.css","script.js"}.issubset(paths):
            return None
        return data
    except:
        return None
