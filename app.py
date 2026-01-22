import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# =========================
# CONFIG
# =========================
MUSICAPI_KEY = os.getenv("MUSICAPI_KEY")

if not MUSICAPI_KEY:
    raise Exception("MUSICAPI_KEY belum di-set di Render Environment Variables")

BASE_URL = "https://api.musicapi.ai/api"
CREATE_URL = f"{BASE_URL}/v1/sonic/create"
STATUS_URL = f"{BASE_URL}/v1/sonic/task"

HEADERS = {
    "Authorization": f"Bearer {MUSICAPI_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# =========================
# REQUEST MODEL
# =========================
class GenerateRequest(BaseModel):
    prompt: str
    title: Optional[str] = None
    mv: str = "sonic-v4-5"
    custom_mode: bool = False
    instrumental: bool = False

# =========================
# 1) GENERATE SONG
# =========================
@app.post("/generate/full-song")
def generate_full_song(req: GenerateRequest):
    payload = req.dict(exclude_none=True)  # FIX PENTING (pydantic v1)

    r = requests.post(CREATE_URL, headers=HEADERS, json=payload, timeout=60)

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()

# =========================
# 2) CHECK STATUS
# =========================
@app.get("/generate/status/{task_id}")
def generate_status(task_id: str):
    r = requests.get(f"{STATUS_URL}/{task_id}", headers=HEADERS, timeout=60)

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    res = r.json()
    data = res.get("data")

    if isinstance(data, list) and len(data) > 0:
        item = data[0]
    elif isinstance(data, dict):
        item = data
    else:
        return {"status": "processing", "raw": res}

    state = item.get("state") or item.get("status")
    audio_url = item.get("audio_url") or item.get("audioUrl") or item.get("audio")

    if state in ["succeeded", "success", "completed", "done"] and audio_url:
        return {"status": "done", "audio_url": audio_url, "result": item}

    return {"status": "processing", "result": item}

# =========================
# 3) STREAM AUDIO
# =========================
@app.get("/audio")
def stream_audio(url: str):
    r = requests.get(url, stream=True, timeout=60)

    if r.status_code != 200:
        raise HTTPException(status_code=404, detail="Audio tidak bisa diambil")

    return StreamingResponse(
        r.iter_content(chunk_size=1024 * 256),
        media_type="audio/mpeg"
    )

# =========================
# ROOT TEST
# =========================
@app.get("/")
def root():
    return {"message": "API jalan bro ✅"}
