import os
import uuid
import time
import requests
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ======================
# ENV
# ======================
DATABASE_URL = os.getenv("DATABASE_URL")
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

if not DATABASE_URL or not SUNO_API_KEY:
    raise RuntimeError("ENV DATABASE_URL / SUNO_API_KEY belum diset")

# ======================
# DATABASE
# ======================
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS songs (
    id SERIAL PRIMARY KEY,
    title TEXT,
    style TEXT,
    audio_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

# ======================
# APP
# ======================
app = FastAPI(title="AI Music API")

# ======================
# SCHEMA
# ======================
class GenerateRequest(BaseModel):
    prompt: str
    title: str
    style: str = "default"

# ======================
# ROUTES
# ======================
@app.get("/")
def root():
    return {"status": "running"}

# ======================
# GENERATE MUSIC (SYNC)
# ======================
@app.post("/generate-music")
def generate_music(data: GenerateRequest):
    task_id = str(uuid.uuid4())

    # 1. Kirim generate ke Suno
    r = requests.post(
        "https://api.suno.ai/generate",
        headers={
            "Authorization": f"Bearer {SUNO_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "prompt": data.prompt,
            "title": data.title,
            "style": data.style,
            "instrumental": False,
            "model": "V4_5"
        },
        timeout=20
    )

    if r.status_code != 200:
        raise HTTPException(500, "Gagal generate musik")

    suno_task_id = r.json().get("data", {}).get("taskId")
    if not suno_task_id:
        raise HTTPException(500, "taskId Suno tidak ada")

    # 2. Polling status Suno
    audio_url = None
    for _ in range(20):  # max ~40 detik
        time.sleep(2)
        s = requests.get(
            f"https://api.suno.ai/status/{suno_task_id}",
            headers={"Authorization": f"Bearer {SUNO_API_KEY}"},
            timeout=10
        )
        data_status = s.json()
        if data_status.get("status") == "completed":
            audio_url = data_status["data"]["audio_url"]
            break

    if not audio_url:
        raise HTTPException(500, "Audio tidak selesai dibuat")

    # 3. Simpan ke DB
    cur.execute(
        "INSERT INTO songs (title, style, audio_url) VALUES (%s,%s,%s)",
        (data.title, data.style, audio_url)
    )

    return {
        "code": 200,
        "msg": "success",
        "audio_url": audio_url
    }

# ======================
# GET SONGS (APK)
# ======================
@app.get("/songs")
def get_songs():
    cur.execute(
        "SELECT id, title, style, audio_url, created_at FROM songs ORDER BY id DESC"
    )
    rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "title": r[1],
            "style": r[2],
            "audio_url": r[3],
            "created_at": r[4]
        }
        for r in rows
    ]
