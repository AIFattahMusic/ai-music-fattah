import os
import httpx
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2

# ================= ENV =================
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

BASE_URL = os.getenv(
    "BASE_URL",
    "https://ai-music-fattah.onrender.com"
)

CALLBACK_URL = f"{BASE_URL}/callback"

SUNO_BASE_API = "https://api.kie.ai/api/v1"
STYLE_GENERATE_URL = f"{SUNO_BASE_API}/style/generate"
MUSIC_GENERATE_URL = f"{SUNO_BASE_API}/generate"
STATUS_URL = f"{SUNO_BASE_API}/generate/record-info"

# ================= APP =================
app = FastAPI(
    title="AI Music Suno API Wrapper",
    version="1.0.2"
)

# ================= MODELS =================
class BoostStyleRequest(BaseModel):
    content: str

class GenerateMusicRequest(BaseModel):
    prompt: str
    style: str
    title: str
    instrumental: bool = False
    customMode: bool = False
    model: str = "V4_5"

# ================= HELPERS =================
def suno_headers():
    if not SUNO_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUNO_API_KEY not set"
        )
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

# ================= ROOT =================
@app.get("/")
def root():
    return {
        "status": "running",
        "service": "AI Music Suno API Wrapper"
    }

# ================= BOOST STYLE =================
@app.post("/boost-style")
async def boost_style(payload: BoostStyleRequest):
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            STYLE_GENERATE_URL,
            headers=suno_headers(),
            json={"content": payload.content}
        )
    return res.json()

# ================= GENERATE MUSIC =================
@app.post("/generate-music")
async def generate_music(payload: GenerateMusicRequest):
    body = {
        "prompt": payload.prompt,
        "customMode": payload.customMode,
        "instrumental": payload.instrumental,
        "model": payload.model,
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

    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=res.text)

    data = res.json()

    task_id = (
        data.get("task_id")
        or data.get("taskId")
        or data.get("id")
        or data.get("data", {}).get("taskId")
    )

    if not task_id:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "task_id not found",
                "response": data
            }
        )

    return {
        "task_id": task_id
    }

# ================= STATUS (NYAMBUNG DENGAN generate-music) =================
@app.get("/generate-music/status/{task_id}")
def generate_music_status(task_id: str):
    r = requests.get(
        f"{STATUS_URL}/{task_id}",
        headers=suno_headers(),
        timeout=30
    )

    if r.status_code != 200:
        raise HTTPException(status_code=404, detail=r.text)

    res = r.json()
    data = res.get("data")

    if not data:
        return {"status": "processing"}

    status = data.get("status") or data.get("state")
    audio_url = (
        data.get("audio_url")
        or data.get("audioUrl")
        or data.get("audio")
    )

    if status in ["pending", "running"]:
        return {"status": "processing"}

    if status == "failed":
        raise HTTPException(status_code=500, detail="Generation failed")

    if status == "succeeded" and audio_url:
        return {
            "status": "done",
            "audio_url": audio_url,
            "result": data
        }

    return {
        "status": "processing",
        "result": data
    }

# ================= DB TEST =================
def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

@app.get("/db-all")
def db_all():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM information_schema.tables
        WHERE table_schema = 'public';
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows
