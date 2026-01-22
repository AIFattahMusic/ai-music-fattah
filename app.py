import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

MUSICAPI_KEY = os.getenv("MUSICAPI_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.musicapi.ai/api")

CREATE_URL = f"{BASE_URL}/v1/sonic/create"
STATUS_URL = f"{BASE_URL}/v1/sonic/task"


def get_headers():
    if not MUSICAPI_KEY:
        raise HTTPException(
            status_code=500,
            detail="MUSICAPI_KEY belum di-set di Render Environment Variables"
        )
    return {
        "Authorization": f"Bearer {MUSICAPI_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }


class GenerateRequest(BaseModel):
    prompt: str
    title: Optional[str] = None
    mv: Optional[str] = "sonic-v4-5"
    custom_mode: Optional[bool] = False
    instrumental: Optional[bool] = False


@app.post("/generate/full-song")
def generate_full_song(req: GenerateRequest):
    payload = req.model_dump(exclude_none=True)

    try:
        r = requests.post(
            CREATE_URL,
            headers=get_headers(),
            json=payload,
            timeout=120
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request ke MusicAPI gagal: {str(e)}")

    # kalau gagal, tampilkan detail jelas
    if r.status_code != 200:
        return {
            "error": "MusicAPI error",
            "status_code": r.status_code,
            "response_text": r.text,
            "payload_sent": payload,
            "create_url": CREATE_URL
        }

    return r.json()


@app.get("/generate/status/{task_id}")
def generate_status(task_id: str):
    try:
        r = requests.get(
            f"{STATUS_URL}/{task_id}",
            headers=get_headers(),
            timeout=120
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request status ke MusicAPI gagal: {str(e)}")

    if r.status_code != 200:
        return {
            "error": "MusicAPI status error",
            "status_code": r.status_code,
            "response_text": r.text,
            "status_url": f"{STATUS_URL}/{task_id}"
        }

    res = r.json()
    data = res.get("data")

    if isinstance(data, list) and len(data) > 0:
        item = data[0]
    elif isinstance(data, dict):
        item = data
    else:
        return {"status": "processing", "result": res}

    state = item.get("state") or item.get("status")
    audio_url = item.get("audio_url") or item.get("audioUrl") or item.get("audio")

    if state in ["succeeded", "success", "completed", "done"] and audio_url:
        return {"status": "done", "audio_url": audio_url, "result": item}

    return {"status": "processing", "result": item}


@app.get("/audio")
def stream_audio(url: str):
    try:
        r = requests.get(
            url,
            stream=True,
            timeout=120,
            headers={"User-Agent": "Mozilla/5.0"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal ambil audio: {str(e)}")

    if r.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Audio tidak bisa diambil. Status={r.status_code}")

    return StreamingResponse(
        r.iter_content(chunk_size=1024 * 256),
        media_type="audio/mpeg"
    )


@app.get("/")
def root():
    return {"message": "API jalan bro ✅"}
