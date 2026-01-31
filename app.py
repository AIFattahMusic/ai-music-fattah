import os
import uuid
from datetime import datetime

import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# =========================
# ENV
# =========================
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_URL = os.environ.get("BASE_URL", "https://ai-music-fattah-1.onrender.com")

# =========================
# DATABASE
# =========================
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

# =========================
# APP
# =========================
app = FastAPI()
os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

# =========================
# SCHEMA
# =========================
class GenerateRequest(BaseModel):
    title: str
    style: str = "default"

class CallbackPayload(BaseModel):
    audio_url: str

# =========================
# ROUTES
# =========================
@app.get("/")
def root():
    return {"ok": True}

# ====== GENERATE (DIPANGGIL APK) ======
@app.post("/generate")
def generate(data: GenerateRequest):
    task_id = str(uuid.uuid4())

    # simpan metadata awal
    cur.execute("""
        INSERT INTO songs (task_id, title, style)
        VALUES (%s,%s,%s)
        ON CONFLICT (task_id) DO NOTHING
    """, (task_id, data.title, data.style))

    # KASIH CALLBACK URL PENUH (INI YANG KAMU MINTA)
    callback_url = f"{BASE_URL}/callback/{task_id}"

    return {
        "task_id": task_id,
        "callback_url": callback_url
    }

# ====== CALLBACK (DIPANGGIL GENERATOR / APK) ======
@app.post("/callback/{task_id}")
def callback(task_id: str, payload: CallbackPayload):
    # simpan file (dummy / ganti isi kalau mau download beneran)
    filename = f"{task_id}.mp3"
    filepath = os.path.join("media", filename)
    with open(filepath, "wb") as f:
        f.write(b"MP3_DATA_FROM_CALLBACK")

    public_audio_url = f"{BASE_URL}/media/{filename}"

    # update DB
    cur.execute("""
        UPDATE songs
        SET audio_url=%s
        WHERE task_id=%s
    """, (public_audio_url, task_id))

    return {
        "status": "saved",
        "audio_url": public_audio_url
    }

# ====== LIST DATA ======
@app.get("/songs")
def songs():
    cur.execute("""
        SELECT id, task_id, title, style, audio_url, created_at
        FROM songs
        ORDER BY id DESC
    """)
    rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "task_id": r[1],
            "title": r[2],
            "style": r[3],
            "audio_url": r[4],
            "created_at": r[5],
        }
        for r in rows
]
