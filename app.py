import os
import httpx
import requests
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# ==================================================
# WAJIB PALING ATAS: BUAT FOLDER MEDIA
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
STYLE_GENERATE_URL = f"{SUNO_BASE_API}/style/generate"
MUSIC_GENERATE_URL = f"{SUNO_BASE_API}/generate"
STATUS_URL = f"{SUNO_BASE_API}/generate/record-info"

# ================= APP =================
app = FastAPI(
    title="AI Music Suno API Wrapper",
    version="1.0.3"
)

# ================= STATIC FILES =================
app.mount("/media", StaticFiles(directory="media"), name="media")

# ================= REQUEST MODEL =================
class BoostStyleRequest(BaseModel):
    content: str

class GenerateMusicRequest(BaseModel):
    prompt: str
    style: Optional[str] = None
    title: Optional[str] = None
    instrumental: bool = False
    customMode: bool = False
    model: str = "V4_5"

# ================= HELPERS =================
def suno_headers():
    if not SUNO_API_KEY:
        raise HTTPException(status_code=500, detail="SUNO_API_KEY not set")
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

def get_db_conn():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

# ================= BASIC =================
@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {"status": "ok"}

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

    return res.json()

# ================= CALLBACK (OPTIONAL LOG) =================
@app.post("/callback")
async def callback(request: Request):
    data = await request.json()
    print("SUNO CALLBACK:", data)
    return {"status": "received"}

# ================= STATUS + AUTO SAVE + AUTO DB =================
@app.get("/generate/status/{task_id}")
def generate_status(task_id: str):
    r = requests.get(
        STATUS_URL,
        headers=suno_headers(),
        params={"taskId": task_id}
    )

    if r.status_code != 200:
        raise HTTPException(status_code=404, detail=r.text)

    res = r.json()

    if not isinstance(res.get("data"), list) or len(res["data"]) == 0:
        return {"status": "processing"}

    item = res["data"][0]
    state = item.get("state") or item.get("status")

    audio_url = (
        item.get("audio_url")
        or item.get("audioUrl")
        or item.get("audio")
    )

    if state != "succeeded" or not audio_url:
        return {"status": "processing"}

    # ================= SAVE MP3 =================
    file_path = f"media/{task_id}.mp3"
    if not os.path.exists(file_path):
        audio_bytes = requests.get(audio_url).content
        with open(file_path, "wb") as f:
            f.write(audio_bytes)

    local_audio_url = f"{BASE_URL}/media/{task_id}.mp3"

    # ================= SAVE DATABASE =================
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO songs (task_id, title, audio_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (task_id) DO NOTHING;
    """, (
        task_id,
        item.get("title"),
        local_audio_url
    ))
    conn.commit()
    cur.close()
    conn.close()

    return {
        "status": "done",
        "task_id": task_id,
        "title": item.get("title"),
        "audio_url": local_audio_url
    }

# ================= DB TEST =================
@app.get("/db-all")
def db_all():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public';
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows
