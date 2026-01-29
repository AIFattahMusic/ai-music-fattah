import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any

# =====================================================
# CONFIG (ENV)
# =====================================================
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

BASE_URL = os.getenv(
    "BASE_URL",
    "https://ai-music-fattah.onrender.com"
)

CALLBACK_URL = f"{BASE_URL}/callback"

SUNO_BASE_API = "https://api.kie.ai/api/v1"

STYLE_GENERATE_URL = f"{SUNO_BASE_API}/style/generate"
MUSIC_GENERATE_URL = f"{SUNO_BASE_API}/generate"
RECORD_INFO_URL = f"{SUNO_BASE_API}/generate/record-info"

if not SUNO_API_KEY:
    raise RuntimeError("SUNO_API_KEY environment variable is required")

# =====================================================
# FASTAPI APP
# =====================================================
app = FastAPI(
    title="AI Music Suno API Wrapper",
    version="1.0.0",
    description="Full FastAPI wrapper for Kie.ai Suno Music API"
)

# =====================================================
# MODELS
# =====================================================
class BoostStyleRequest(BaseModel):
    content: str

class GenerateMusicRequest(BaseModel):
    prompt: str
    style: Optional[str] = None
    title: Optional[str] = None
    instrumental: bool = False
    customMode: bool = True
    model: str = "V4_5"

class RecordInfoResponse(BaseModel):
    code: int
    msg: str
    data: Dict[str, Any]

# =====================================================
# HELPERS
# =====================================================
def suno_headers():
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

# =====================================================
# ENDPOINTS
# =====================================================

@app.get("/")
def root():
    return {
        "service": "AI Music Suno API",
        "status": "running",
        "endpoints": {
            "boost_style": "POST /boost-style",
            "generate_music": "POST /generate-music",
            "record_info": "GET /record-info/{task_id}",
            "callback": "POST /callback",
            "health": "GET /health"
        }
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# =====================================================
# 1️⃣ BOOST MUSIC STYLE
# =====================================================
@app.post("/boost-style")
async def boost_music_style(payload: BoostStyleRequest):
    """
    Boost / enhance music style description
    """
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            STYLE_GENERATE_URL,
            headers=suno_headers(),
            json={
                "content": payload.content
            }
        )

    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)

    return res.json()

# =====================================================
# 2️⃣ GENERATE MUSIC
# =====================================================
@app.post("/generate-music")
async def generate_music(payload: GenerateMusicRequest):
    """
    Generate music using Suno API (async task)
    """
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
        raise HTTPException(res.status_code, res.text)

    return res.json()

# =====================================================
# 3️⃣ GET RECORD INFO (Polling)
# =====================================================
@app.get("/record-info/{task_id}", response_model=RecordInfoResponse)
async def get_record_info(task_id: str):
    """
    Get music generation result / status
    """
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(
            RECORD_INFO_URL,
            headers=suno_headers(),
            params={"taskId": task_id}
        )

    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)

    return res.json()

# =====================================================
# 4️⃣ CALLBACK (WEBHOOK)
# =====================================================
@app.post("/callback")
async def suno_callback(request: Request):
    """
    Receive async callback from Suno API
    """
    data = await request.json()

    # LOG ONLY (replace with DB if needed)
    print("========== SUNO CALLBACK ==========")
    print(data)
    print("===================================")

    return {
        "status": "received",
        "success": True
    }

