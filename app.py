import os
import time
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://api.kie.ai").rstrip("/")

if not API_KEY:
    print("❌ ENV API_KEY belum di set")


class GenerateRequest(BaseModel):
    prompt: str


@app.get("/")
def root():
    return {"status": "ok", "message": "AI Music API running"}


def generate_music(prompt: str):
    url = f"{BASE_URL}/api/v1/generate"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    payload = {
        "customMode": False,
        "instrumental": False,
        "model": "V3",
        "prompt": prompt,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=60)

    # kalau API ngasih error
    if r.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Generate gagal {r.status_code}: {r.text}"
        )

    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=500, detail=f"Response bukan JSON: {r.text}")

    # DEBUG biar keliatan bentuk response asli
    if "data" not in data:
        raise HTTPException(status_code=500, detail=f"Response tidak ada 'data': {data}")

    if "taskId" not in data["data"]:
        raise HTTPException(status_code=500, detail=f"Response tidak ada 'taskId': {data}")

    return data["data"]["taskId"]


def wait_task(task_id: str):
    url = f"{BASE_URL}/api/v1/music/task/{task_id}"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json",
    }

    for _ in range(60):  # max 60x cek
        r = requests.get(url, headers=headers, timeout=30)

        if r.status_code != 200:
            time.sleep(2)
            continue

        try:
            data = r.json()
        except Exception:
            time.sleep(2)
            continue

        # cek struktur response
        if "data" in data and "status" in data["data"]:
            status = data["data"]["status"]

            # sukses biasanya ada sunoData
            if status == "SUCCESS":
                try:
                    audio_url = data["data"]["response"]["sunoData"][0]["audioUrl"]
                    return audio_url
                except Exception:
                    raise HTTPException(status_code=500, detail=f"SUCCESS tapi audioUrl tidak ada: {data}")

        time.sleep(2)

    raise HTTPException(status_code=504, detail="Timeout: audio belum jadi")


@app.post("/generate-song")
def generate_song(data: GenerateRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY belum diset di Render")

    task_id = generate_music(data.prompt)
    audio_url = wait_task(task_id)

    return {"status": "success", "task_id": task_id, "audio_url": audio_url}
