import os
import uuid
import requests
from datetime import datetime

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# =====================
# ENV
# =====================
DATABASE_URL = os.environ.get("DATABASE_URL")
SUNO_API_KEY = os.environ.get("SUNO_API_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://ai-music-fattah-1.onrender.com")

if not DATABASE_URL or not SUNO_API_KEY:
    raise RuntimeError("ENV DATABASE_URL / SUNO_API_KEY belum diset")

# =====================
# DATABASE
# =====================
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

# =====================
# APP
# =====================
app = FastAPI()

os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

# =====================
# SCHEMA
# =====================
class GenerateRequest(BaseModel):
    title: str
    style: str = "default"

class CallbackPayload(BaseModel):
    audio_url: str

# =====================
# ROUTES
# =====================
@app.get("/")
def root():
    return {"ok": True}

# ========= GENERATE (DIPANGGIL APK) =========
@app.post("/generate")
def generate(data: GenerateRequest):
    task_id = str(uuid.uuid4())

    cur.execute(
        "INSERT INTO songs (task_id, title, style) VALUES (%s,%s,%s)",
        (task_id, data.title, data.style)
    )

    callback_url = f"{BASE_URL}/callback/{task_id}"

    # === CONTOH HIT API SUNO / AI MUSIC (ASYNC CALLBACK) ===
    # GANTI ENDPOINT INI SESUAI PROVIDER KAMU
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
        "callback_url": callback_url
    }

# ========= CALLBACK (INI YANG KAMU TERIAKIN) =========
@app.post("/callback/{task_id}")
def callback(task_id: str, payload: CallbackPayload):
    try:
        r = requests.get(payload.audio_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"download gagal: {e}")

    filename = f"{task_id}.mp3"
    filepath = os.path.join("media", filename)

    with open(filepath, "wb") as f:
        f.write(r.content)

    public_url = f"{BASE_URL}/media/{filename}"

    cur.execute(
        "UPDATE songs SET audio_url=%s WHERE task_id=%s",
        (public_url, task_id)
    )

    return {
        "task_id": task_id,
        "audio_url": public_url
    }

# ========= CEK DATABASE =========
@app.get("/songs")
def list_songs():
    cur.execute(
        "SELECT task_id, title, style, audio_url, created_at FROM songs ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    return [
        {
            "task_id": r[0],
            "title": r[1],
            "style": r[2],
            "audio_url": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]
