import os
import time
import requests
import psycopg2

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# =========================
# ENV
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

if not DATABASE_URL or not SUNO_API_KEY:
    raise RuntimeError("ENV DATABASE_URL / SUNO_API_KEY belum diset")

# =========================
# DATABASE
# =========================
conn = psycopg2.connect(DATABASE_URL)
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
    prompt: str
    style: str = "reggae"
    title: str = "Untitled"

# =========================
# ROUTES
# =========================
@app.get("/")
def root():
    return {"ok": True}

@app.post("/generate")
def generate_music(data: GenerateRequest):
    # 1. KIRIM KE SUNO
    res = requests.post(
        "https://api.suno.ai/v1/generate",
        headers={
            "Authorization": f"Bearer {SUNO_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": data.prompt,
            "style": data.style,
            "title": data.title,
        },
        timeout=60
    )

    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Gagal generate")

    result = res.json()
    task_id = result["task_id"]

    # 2. POLLING SAMPAI JADI
    audio_url = None
    for _ in range(30):
        time.sleep(5)
        check = requests.get(
            f"https://api.suno.ai/v1/task/{task_id}",
            headers={"Authorization": f"Bearer {SUNO_API_KEY}"},
            timeout=30
        ).json()

        if check.get("status") == "completed":
            audio_url = check["audio_url"]
            break

    if not audio_url:
        raise HTTPException(status_code=500, detail="Audio tidak selesai")

    # 3. SIMPAN KE DATABASE (INI YANG KEMARIN HILANG)
    cur.execute("""
        INSERT INTO songs (task_id, title, style, audio_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (task_id) DO NOTHING
    """, (task_id, data.title, data.style, audio_url))

    return {
        "task_id": task_id,
        "title": data.title,
        "style": data.style,
        "audio_url": audio_url
    }

@app.get("/songs")
def list_songs():
    cur.execute("""
        SELECT id, title, style, audio_url, created_at
        FROM songs
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "title": r[1],
            "style": r[2],
            "audio_url": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]
