import os
import httpx
import requests
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# ==================================================
# WAJIB PALING ATAS
# ==================================================
os.makedirs("media", exist_ok=True)

# ================= ENV =================
SUNO_API_KEY = os.getenv("SUNO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

BASE_URL = os.getenv(
    "BASE_URL",
    "https://ai-music-fattah.onrender.com"
)

CALLBACK_URL = f"{BASE_URL}/callback"

SUNO_BASE_API = "https://api.kie.ai/api/v1"
MUSIC_GENERATE_URL = f"{SUNO_BASE_API}/generate"
STATUS_URL = f"{SUNO_BASE_API}/generate/record-info"

# ================= APP =================
app = FastAPI(title="Fattah AI Music API", version="1.0.0")
app.mount("/media", StaticFiles(directory="media"), name="media")

# ================= DB =================
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ================= MODELS =================
class GenerateMusicRequest(BaseModel):
    prompt: str
    style: Optional[str] = None
    title: Optional[str] = None

# ================= HELPERS =================
def suno_headers():
    if not SUNO_API_KEY:
        raise HTTPException(500, "SUNO_API_KEY not set")
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

# ================= ENDPOINTS =================
@app.get("/")
def root():
    return {"status": "ok"}

# ---------------- GENERATE ----------------
@app.post("/generate-music")
async def generate_music(payload: GenerateMusicRequest):
    body = {
        "prompt": payload.prompt,
        "model": "V4_5",
        "callBackUrl": CALLBACK_URL
    }
    if payload.style:
        body["style"] = payload.style
    if payload.title:
        body["title"] = payload.title

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            MUSIC_GENERATE_URL,
            headers=suno_headers(),
            json=body
        )
    return res.json()

# ---------------- STATUS + SAVE ----------------
@app.get("/generate/status/{task_id}")
def generate_status(task_id: str):
    r = requests.get(
        STATUS_URL,
        headers=suno_headers(),
        params={"taskId": task_id}
    )

    if r.status_code != 200:
        raise HTTPException(404, r.text)

    res = r.json()
    data = res.get("data", [])
    if not data:
        return {"status": "processing"}

    item = data[0]
    state = item.get("state")
    audio_url = item.get("audio_url") or item.get("audioUrl")

    if state != "succeeded" or not audio_url:
        return {"status": state}

    # DOWNLOAD MP3
    audio_bytes = requests.get(audio_url).content
    file_path = f"media/{task_id}.mp3"
    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    public_audio_url = f"{BASE_URL}/media/{task_id}.mp3"

    # SAVE TO DB
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO songs (task_id, title, style, audio_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (task_id) DO NOTHING
    """, (
        task_id,
        item.get("title"),
        item.get("style"),
        public_audio_url
    ))
    conn.commit()
    cur.close()
    conn.close()

    return {
        "status": "done",
        "audio_url": public_audio_url
    }

# ---------------- LIST SONGS ----------------
@app.get("/songs")
def list_songs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, task_id, title, style, audio_url, created_at
        FROM songs
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": r[0],
            "task_id": r[1],
            "title": r[2],
            "style": r[3],
            "audio_url": r[4],
            "created_at": r[5]
        }
        for r in rows
    ]
