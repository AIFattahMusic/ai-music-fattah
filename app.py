import os
import uuid
import requests
import httpx
import psycopg2

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# ==================================================
# SETUP
# ==================================================
os.makedirs("media", exist_ok=True)

SUNO_API_KEY = os.getenv("SUNO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

BASE_URL = os.getenv(
    "BASE_URL",
    "https://ai-music-fattah.onrender.com"
)

CALLBACK_URL = f"{BASE_URL}/callback"

SUNO_BASE_API = "https://api.kie.ai/api/v1"
STYLE_GENERATE_URL = f"{SUNO_BASE_API}/style/generate"
MUSIC_GENERATE_URL = f"{SUNO_BASE_API}/generate"
STATUS_URL = f"{SUNO_BASE_API}/generate/record-info"

# ==================================================
# APP
# ==================================================
app = FastAPI(title="AI Music API", version="1.0.0")
app.mount("/media", StaticFiles(directory="media"), name="media")

# ==================================================
# MODELS
# ==================================================
class GenerateMusicRequest(BaseModel):
    prompt: str
    title: Optional[str] = None
    style: Optional[str] = None
    instrumental: bool = False
    customMode: bool = False
    model: str = "V4_5"

# ==================================================
# HELPERS
# ==================================================
def suno_headers():
    if not SUNO_API_KEY:
        raise HTTPException(500, "SUNO_API_KEY not set")
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

def get_conn():
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

def insert_song(task_id, title, audio_url, file_path):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO songs (task_id, title, audio_url, file_path)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (task_id) DO NOTHING
    """, (task_id, title, audio_url, file_path))
    conn.commit()
    cur.close()
    conn.close()

# ==================================================
# ENDPOINTS
# ==================================================
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/generate-music")
async def generate_music(payload: GenerateMusicRequest):
    body = {
        "prompt": payload.prompt,
        "instrumental": payload.instrumental,
        "customMode": payload.customMode,
        "model": payload.model,
        "callBackUrl": CALLBACK_URL
    }

    if payload.title:
        body["title"] = payload.title
    if payload.style:
        body["style"] = payload.style

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            MUSIC_GENERATE_URL,
            headers=suno_headers(),
            json=body
        )

    return res.json()

@app.get("/generate/status/{task_id}")
def generate_status(task_id: str):
    r = requests.get(
        STATUS_URL,
        headers=suno_headers(),
        params={"taskId": task_id}
    )

    if r.status_code != 200:
        raise HTTPException(404, r.text)

    data = r.json().get("data", [])
    if not data:
        return {"status": "processing"}

    item = data[0]
    state = item.get("state") or item.get("status")
    audio_url = item.get("audio_url") or item.get("audioUrl")

    if state != "succeeded" or not audio_url:
        return {"status": "processing"}

    # ================= DOWNLOAD AUDIO =================
    audio_bytes = requests.get(audio_url).content

    filename = f"{uuid.uuid4()}.mp3"
    file_path = f"media/{filename}"

    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    public_url = f"{BASE_URL}/media/{filename}"

    # ================= INSERT DATABASE =================
    insert_song(
        task_id=task_id,
        title=item.get("title"),
        audio_url=public_url,
        file_path=file_path
    )

    return {
        "status": "done",
        "audio_url": public_url,
        "title": item.get("title")
    }

@app.post("/callback")
async def callback(request: Request):
    data = await request.json()
    # callback tidak wajib insert (pakai polling)
    return {"ok": True}

@app.get("/songs")
def get_songs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, audio_url, created_at
        FROM songs
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return rows
