import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# =========================
# ENV (WAJIB DI RENDER)
# =========================
API_KEY = os.getenv("SUNO_API_KEY")
if not API_KEY:
    raise RuntimeError("SUNO_API_KEY tidak ditemukan")

# =========================
# APP
# =========================
app = FastAPI(title="KIE.AI Music Generator")

@app.get("/")
def root():
    return {"status": "OK", "message": "KIE.AI Music API running"}

# =========================
# REQUEST MODEL
# =========================
class GenerateMusic(BaseModel):
    style: str
    title: str
    prompt: str
    customMode: bool = True
    instrumental: bool = False   # ⬅️ PENTING: false = ADA VOKAL

# =========================
# GENERATE MUSIC (VOKAL)
# =========================
@app.post("/generate-music")
async def generate_music(req: GenerateMusic):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "V4_5",
        "style": req.style,
        "title": req.title,
        "prompt": req.prompt,
        "customMode": req.customMode,
        "instrumental": False  # PAKSA VOKAL
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.kie.ai/api/v1/generate/music",
            headers=headers,
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
