import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# =========================
# CONFIG MUSICAPI
# =========================
MUSICAPI_KEY = os.getenv("MUSICAPI_KEY")

if not MUSICAPI_KEY:
    raise Exception("MUSICAPI_KEY belum diset. Set di Render Environment Variables.")

MUSICAPI_CREATE_URL = "https://api.musicapi.ai/api/v1/sonic/create"
MUSICAPI_STATUS_URL = "https://api.musicapi.ai/api/v1/sonic/task"

HEADERS = {
    "Authorization": f"Bearer {MUSICAPI_KEY}",
    "Content-Type": "application/json"
}

# =========================
# REQUEST MODEL
# =========================
class GenerateRequest(BaseModel):
    prompt: str
    title: Optional[str] = "Lagu AI"
    mv: Optional[str] = "sonic-v4-5"
    custom_mode: Optional[bool] = False
    instrumental: Optional[bool] = False


# =========================
# 1) GENERATE FULL SONG
# =========================
@app.post("/generate/full-song")
def generate_full_song(req: GenerateRequest):
    payload = {
        "prompt": req.prompt,
        "title": req.title,
        "mv": req.mv,
        "custom_mode": req.custom_mode,
        "instrumental": req.instrumental
    }

    r = requests.post(MUSICAPI_CREATE_URL, headers=HEADERS, json=payload)

    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text)

    return r.json()


# =========================
# 2) CHECK STATUS
# =========================
@app.get("/generate/status/{task_id}")
def generate_status(task_id: str):
    r = requests.get(f"{MUSICAPI_STATUS_URL}/{task_id}", headers=HEADERS)

    if r.status_code != 200:
        raise HTTPException(status_code=404, detail=r.text)

    res = r.json()

    # ambil data item pertama
    item = None
    if isinstance(res.get("data"), list) and len(res["data"]) > 0:
        item = res["data"][0]

    if not item:
        return {"status": "processing", "result": res}

    state = item.get("state") or item.get("status")
    audio_url = item.get("audio_url") or item.get("audioUrl") or item.get("audio")

    # kalau sudah selesai dan ada audio
    if state == "succeeded" and audio_url:
        return {"status": "done", "audio_url": audio_url, "result": item}

    return {"status": "processing", "result": item}


# =========================
# 3) STREAM AUDIO (BIAR BISA DIBUKA)
# =========================
@app.get("/audio")
def stream_audio(url: str):
    r = requests.get(url, stream=True)

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
