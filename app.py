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

# ==================================================
# STATIC FILES
# ==================================================
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
        raise HTTPException(
            status_code=500,
            detail="SUNO_API_KEY not set in environment"
        )
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

def normalize_model(model: str) -> str:
    if model.lower() in ["v4", "v4_5", "v45"]:
        return "V4_5"
    return model

# ================= ENDPOINTS =================
@app.get("/")
def root():
    return {"status": "running", "service": "AI Music Suno API"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/boost-style")
async def boost_style(payload: BoostStyleRequest):
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            STYLE_GENERATE_URL,
            headers=suno_headers(),
            json={"content": payload.content}
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
        raise HTTPException(status_code=404, detail=r.text)

    res = r.json()

    item = None
    if isinstance(res.get("data"), list) and len(res["data"]) > 0:
        item = res["data"][0]

    if not item:
        return {"status": "processing", "result": res}

    state = item.get("state") or item.get("status")
    audio_url = (
        item.get("audio_url")
        or item.get("audioUrl")
        or item.get("audio")
    )

    if state == "succeeded" and audio_url:
        # ===== SIMPAN MP3 =====
        audio_bytes = requests.get(audio_url).content
        file_path = f"media/{task_id}.mp3"
        with open(file_path, "wb") as f:
            f.write(audio_bytes)

        local_audio_url = f"{BASE_URL}/media/{task_id}.mp3"

        # ===== SIMPAN KE DATABASE (INI YANG DARI TADI TIDAK ADA) =====
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
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
            "audio_url": local_audio_url
        }

    return {"status": "processing", "result": item}

        item = items[0]

        state = item.get("state") or item.get("status")
        if state != "succeeded":
            return {"status": "processing"}

        
