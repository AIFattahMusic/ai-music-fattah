import os
import httpx
from fastapi import FastAPI, Request, HTTPException

SUNO_API_KEY = os.getenv("SUNO_API_KEY")
DB_API_URL = "https://ai-music-fattah-1.onrender.com/save"

SUNO_BASE = "https://api.kie.ai/api/v1"
GENERATE_URL = f"{SUNO_BASE}/generate"
RECORD_URL = f"{SUNO_BASE}/generate/record-info"

app = FastAPI(title="AI Music Generator")

def headers():
    if not SUNO_API_KEY:
        raise HTTPException(500, "SUNO_API_KEY not set")
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/generate-music")
async def generate_music(req: dict):
    body = {
        "prompt": req.get("prompt"),
        "style": req.get("style"),
        "title": req.get("title"),
        "instrumental": req.get("instrumental", False),
        "customMode": True,
        "model": "V4_5",
        "callBackUrl": "https://ai-music-fattah.onrender.com/callback"
    }

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(GENERATE_URL, headers=headers(), json=body)

    return r.json()

@app.get("/record-info/{task_id}")
async def record_info(task_id: str):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(RECORD_URL, headers=headers(), params={"taskId": task_id})
    return r.json()

@app.post("/callback")
async def callback(request: Request):
    data = await request.json()

    async with httpx.AsyncClient(timeout=20) as c:
        await c.post(DB_API_URL, json=data)

    return {"status": "saved_to_database"}
