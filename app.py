import os
import uuid
import requests
import psycopg2
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ======================================================
# ENV
# ======================================================
DATABASE_URL = os.environ.get("DATABASE_URL")
SUNO_API_KEY = os.environ.get("SUNO_API_KEY")
BASE_URL = os.environ.get("BASE_URL")  # contoh: https://ai-music-fattah-1.onrender.com

if not DATABASE_URL or not SUNO_API_KEY or not BASE_URL:
    raise RuntimeError("ENV DATABASE_URL / SUNO_API_KEY / BASE_URL belum diset")

# ======================================================
# DATABASE
# ======================================================
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
    status TEXT DEFAULT 'processing',
    created_at TIMESTAMP DEFAULT NOW()
);
""")

# ======================================================
# APP
# ======================================================
app = FastAPI(title="AI Music API", version="1.0.0")

# ======================================================
# SCHEMA
# ======================================================
class GenerateMusicRequest(BaseModel):
    title: str
    style: str = "default"

class CallbackPayload(BaseModel):
    audio_url: str

# ======================================================
# ROOT
# ======================================================
@app.get("/")
def root():
    return {"status": "running"}

# ======================================================
# GENERATE MUSIC (DIPANGGIL APK)
# ======================================================
@app.post("/generate-music")
def generate_music(data: GenerateMusicRequest):
    task_id = str(uuid.uuid4())

    # simpan task awal
    cur.execute(
        """
        INSERT INTO songs (task_id, title, style, status)
        VALUES (%s, %s, %s, %s)
        """,
        (task_id, data.title, data.style, "processing")
    )

    callback_url = f"{BASE_URL}/callback/{task_id}"

    # panggil provider (ASYNC)
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
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": task_id
        }
    }

# ======================================================
# CALLBACK (DIPANGGIL PROVIDER)
# ======================================================
@app.post("/callback/{task_id}")
def callback(task_id: str, payload: CallbackPayload):
    if not payload.audio_url:
        raise HTTPException(status_code=400, detail="audio_url kosong")

    cur.execute(
        """
        UPDATE songs
        SET audio_url=%s, status=%s
        WHERE task_id=%s
        """,
        (payload.audio_url, "done", task_id)
    )

    return {"ok": True}

# ======================================================
# CEK STATUS (DIPANGGIL APK)
# ======================================================
@app.get("/generate/status/{task_id}")
def get_status(task_id: str):
    cur.execute(
        """
        SELECT task_id, title, style, audio_url, status, created_at
        FROM songs
        WHERE task_id=%s
        """,
        (task_id,)
    )
    row = cur.fetchone()

    # ⬅️ INI PENTING: JANGAN 500
    if row is None:
        return {
            "task_id": task_id,
            "status": "processing",
            "audio_url": None
        }

    return {
        "task_id": row[0],
        "title": row[1],
        "style": row[2],
        "audio_url": row[3],
        "status": row[4],
        "created_at": row[5]
    }

# ======================================================
# LIST SEMUA LAGU (OPTIONAL)
# ======================================================
@app.get("/songs")
def list_songs():
    cur.execute(
        """
        SELECT task_id, title, style, audio_url, status, created_at
        FROM songs
        ORDER BY created_at DESC
        """
    )
    rows = cur.fetchall()

    return [
        {
            "task_id": r[0],
            "title": r[1],
            "style": r[2],
            "audio_url": r[3],
            "status": r[4],
            "created_at": r[5]
        }
        for r in rows
    ]
