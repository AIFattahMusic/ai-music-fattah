import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# =========================
# CONFIG MUSICAPI
# =========================
MUSICAPI_KEY = os.getenv("MUSICAPI_KEY")

if not MUSICAPI_KEY:
    raise Exception("MUSICAPI_KEY belum diset. Jalankan: set MUSICAPI_KEY=APIKEYKAMU")

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
    mv: str = "sonic-v4-5"
    custom_mode: bool = False
    gpt_description_prompt: str
    tags: Optional[str] = ""

# =========================
# ENDPOINT 1: GENERATE FULL SONG
# =========================
@app.post("/generate/full-song")
def generate_full_song(data: GenerateRequest):
    payload = {
        "mv": data.mv,
        "custom_mode": data.custom_mode,
        "gpt_description_prompt": data.gpt_description_prompt,
        "tags": data.tags
    }

    try:
        r = requests.post(MUSICAPI_CREATE_URL, headers=HEADERS, json=payload, timeout=60)

        # kalau error dari MusicAPI, tampilkan jelas
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)

        return r.json()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# ENDPOINT 2: CEK STATUS TASK
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

from fastapi import FastAPI

app = FastAPI()

@app.get("/gallery")
def get_gallery():
    return [
        {
            "id": 1,
            "title": "Lagu 1",
            "imageUrl": "https://picsum.photos/400/400",
            "audioUrl": "https://example.com/audio1.mp3"
        },
        {
            "id": 2,
            "title": "Lagu 2",
            "imageUrl": "https://picsum.photos/401/401",
            "audioUrl": "https://example.com/audio2.mp3"
        }
    ]
