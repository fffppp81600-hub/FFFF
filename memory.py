from typing import Optional

memory: dict = {}


def set_last(user_id: str, project: dict):
    memory[user_id] = project


def get_last(user_id: str) -> Optional[dict]:
    return memory.get(user_id)


def clear(user_id: str):
    memory.pop(user_id, None)
