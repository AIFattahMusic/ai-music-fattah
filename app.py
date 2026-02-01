import os
import uuid
import httpx
import requests
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# ================= SETUP =================
os.makedirs("media", exist_ok=True)

SUNO_API_KEY = os.getenv("SUNO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
BASE_URL = os.getenv("BASE_URL", "https://ai-music-fattah.onrender.com")

CALLBACK_URL = f"{BASE_URL}/callback"

SUNO_BASE_API = "https://api.kie.ai/v1"
MUSIC_GENERATE_URL = f"{SUNO_BASE_API}/music"
STATUS_URL = f"{SUNO_BASE_API}/music"

app = FastAPI(
    title="AI Music API",
    version="1.0.3"
)

app.mount("/media", StaticFiles(directory="media"), name="media")

# ================= MODELS =================
class GenerateMusicRequest(BaseModel):
    prompt: str
    style: Optional[str] = None
    title: Optional[str] = None
    instrumental: bool = False
    model: str = "v4"

# ================= HELPERS =================
def suno_headers():
    if not SUNO_API_KEY:
        raise HTTPException(500, "SUNO_API_KEY not set")
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

# ================= ROOT =================
@app.get("/")
def root():
    return {"status": "running"}

# ================= GENERATE =================
@app.post("/generate-music")
async def generate_music(payload: GenerateMusicRequest):
    body = {
        "prompt": payload.prompt,
        "instrumental": payload.instrumental,
        "model": payload.model,
        "callback_url": CALLBACK_URL
    }

    if payload.style:
        body["style"] = payload.style
    if payload.title:
        body["title"] = payload.title

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            MUSIC_GENERATE_URL,
            headers=suno_headers(),
            json=body
        )

    data = r.json()

    if "task_id" not in data:
        raise HTTPException(500, data)

    return {
        "code": 200,
        "msg": "success",
        "taskId": data["task_id"]
    }

# ================= STATUS =================
@app.get("/generate/status/{task_id}")
def generate_status(task_id: str):
    r = requests.get(
        f"{STATUS_URL}/{task_id}",
        headers=suno_headers(),
        timeout=20
    )

    if r.status_code != 200:
        raise HTTPException(500, r.text)

    data = r.json()

    if data.get("status") != "completed":
        return {"status": "processing", "raw": data}

    audio_url = data.get("audio_url")
    if not audio_url:
        raise HTTPException(500, "audio_url missing")

    audio = requests.get(audio_url).content

    filename = f"{uuid.uuid4()}.mp3"
    path = f"media/{filename}"

    with open(path, "wb") as f:
        f.write(audio)

    return {
        "status": "done",
        "audio_url": f"{BASE_URL}/media/{filename}"
    }

# ================= CALLBACK =================
@app.post("/callback")
async def callback(req: Request):
    data = await req.json()
    print("CALLBACK:", data)
    return {"ok": True}

# ================= DB TEST =================
def get_conn():
    return psycopg2.connect(DATABASE_URL)

@app.get("/db-test")
def db_test():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    cur.close()
    conn.close()
    return {"db": "ok"}
