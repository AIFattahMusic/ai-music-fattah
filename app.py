from fastapi import FastAPI, Request
import requests
import time
import os

app = FastAPI()

API_KEY = os.getenv("API_KEY")
BASE_URL = "https://api.kie.ai"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def generate_music(prompt: str):
    payload = {
        "customMode": False,
        "instrumental": False,
        "model": "V5",
        "prompt": prompt,
        "callBackUrl": "http://127.0.0.1:8000/callback"
    }

    r = requests.post(
        f"{BASE_URL}/api/v1/generate",
        headers=HEADERS,
        json=payload
    )
    return r.json()["data"]["taskId"]

def wait_task(task_id: str):
    while True:
        r = requests.get(
            f"{BASE_URL}/music/task/{task_id}",
            headers=HEADERS
        )
        data = r.json()["data"]
        if data["status"] == "SUCCESS":
            return data["response"]["sunoData"][0]["audioUrl"]
        time.sleep(3)

@app.post("/generate-song")
def generate_song(data: dict):
    task_id = generate_music(data["prompt"])
    audio_url = wait_task(task_id)
    return {"audioUrl": audio_url}

@app.post("/callback")
async def callback(req: Request):
    payload = await req.json()
    print(payload)
    return {"status": "ok"}

@app.get("/")
def root():
    return {"status": "API hidup"}