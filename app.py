import os
import uuid
import requests
import psycopg2
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ======================
# ENV
# ======================
DATABASE_URL = os.environ.get("DATABASE_URL")
SUNO_API_KEY = os.environ.get("SUNO_API_KEY")
BASE_URL = os.environ.get("BASE_URL")  # ex: https://ai-music-fattah.onrender.com

if not DATABASE_URL or not SUNO_API_KEY or not BASE_URL:
    raise RuntimeError("ENV DATABASE_URL / SUNO_API_KEY / BASE_URL belum diset")

# ======================
# DATABASE
# ======================
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS songs (
    id SERIAL PRIMARY KEY,
    task_id TEXT UNIQUE,
    title TEXT,
    style TEXT,
    audio_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

# ======================
# APP
# ======================
app = FastAPI()

os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

# ======================
# SCHEMA
# ======================
class GenerateRequest(BaseModel):
    title: str
    style: str = "default"

class CallbackPayload(BaseModel):
    audio_url: str

# ======================
# ROUTES
# ======================
@app.get("/")
def root():
    return {"ok": True}

# ======================
# GENERATE (DIPANGGIL APK)
# ======================
@app.post("/generate")
def generate(data: GenerateRequest):
    task_id = str(uuid.uuid4())

    # simpan metadata awal
    cur.execute(
        "INSERT INTO songs (task_id, title, style) VALUES (%s,%s,%s)",
        (task_id, data.title, data.style)
    )

    callback_url = f"{BASE_URL}/callback/{task_id}"

    # panggil provider (ASYNC CALLBACK)
    try:
        requests.post(
            "https://api.suno.ai/generate",
            headers={
                "Authorization": f"Bearer {SUNO_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "title": data.title,
                "style": data.style,
                "callback_url": callback_url
            },
            timeout=10
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "task_id": task_id,
        "status": "processing",
        "callback_url": callback_url
    }

# ======================
# CALLBACK (DIPANGGIL PROVIDER)
# ======================
@app.post("/callback/{task_id}")
def callback(task_id: str, payload: CallbackPayload):
    audio_url = payload.audio_url

    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url kosong")

    # simpan ke DB
    cur.execute(
        "UPDATE songs SET audio_url=%s WHERE task_id=%s",
        (audio_url, task_id)
    )

    return {"ok": True}

# ======================
# CEK STATUS (DIPANGGIL APK)
# ======================
@app.get("/status/{task_id}")
def status(task_id: str):
    cur.execute(
        "SELECT task_id, title, style, audio_url, created_at FROM songs WHERE task_id=%s",
        (task_id,)
    )
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="task_id tidak ditemukan")

    return {
        "task_id": row[0],
        "title": row[1],
        "style": row[2],
        "audio_url": row[3],
        "created_at": row[4]
    }

