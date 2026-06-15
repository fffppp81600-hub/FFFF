from datetime import datetime
import os

def log(msg):
    os.makedirs("logs", exist_ok=True)
    print(f"[{datetime.now()}] {msg}")