import json

def safe_parse(text):
    try:
        return json.loads(text)
    except:
        return None