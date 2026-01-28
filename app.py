import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# =====================================================
# KIE.AI CONFIG
# =====================================================
KIE_API_KEY = os.getenv("KIE_API_KEY")
if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY tidak ditemukan di environment")

KIE_GENERATE_URL = "https://api.kie.ai/api/v1/generate/music"

HEADERS = {
    "Authorization": f"Bearer {KIE_API_KEY}",
    "Content-Type": "application/json"
}

# =====================================================
# APP
# =====================================================
app = FastAPI(title="KIE.AI Music Generator")

@app.get("/")
def root():
    return {
        "status": "OK",
        "provider": "KIE.AI",
        "message": "Music generator running"
    }

# =====================================================
# REQUEST MODEL
# =====================================================
class GenerateMusic(BaseModel):
    style: str
    title: str
    prompt: str
    instrumental: bool = False  # false = ADA VOKAL

# =====================================================
# GENERATE MUSIC (VOKAL)
# =====================================================
@app.post("/generate-music")
async def generate_music(req: GenerateMusic):
    payload = {
        "model": "V4_5",
        "style": req.style,
        "title": req.title,
        "prompt": req.prompt,
        "customMode": True,
        "instrumental": False  # PAKSA ADA VOKAL
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            KIE_GENERATE_URL,
            headers=HEADERS,
            json=payload
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail={
                "kie_status": response.status_code,
                "kie_response": response.text
            }
        )

    return response.json()
