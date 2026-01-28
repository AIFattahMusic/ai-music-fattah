import os
import uuid
import requests
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

# ================= ENV =================
KIE_API_KEY = os.getenv("KIE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")

if not all([KIE_API_KEY, DATABASE_URL, CALLBACK_URL]):
    raise RuntimeError("ENV BELUM LENGKAP")

# ================= KIE API =================
KIE_GENERATE_URL = "https://api.kie.ai/api/v1/generate/music"

# ================= DATABASE =================
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Music(Base):
    __tablename__ = "musics"

    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    style = Column(String)
    prompt = Column(String)
    instrumental = Column(Boolean)
    status = Column(String)
    audio_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ================= FASTAPI =================
app = FastAPI(title="AI Music Generator")

class GenerateReq(BaseModel):
    style: str
    title: str
    prompt: str
    instrumental: bool = False

# ================= GENERATE MUSIC =================
@app.post("/generate-music")
def generate_music(data: GenerateReq):
    db = SessionLocal()
    try:
        music_id = str(uuid.uuid4())

        music = Music(
            id=music_id,
            title=data.title,
            style=data.style,
            prompt=data.prompt,
            instrumental=data.instrumental,
            status="pending"
        )

        db.add(music)
        db.commit()

        payload = {
            "style": data.style,
            "title": data.title,
            "prompt": data.prompt,
            "instrumental": data.instrumental,
            "callback_url": CALLBACK_URL,
            "external_id": music_id
        }

        res = requests.post(
            KIE_GENERATE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {KIE_API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        if res.status_code != 200:
            raise HTTPException(500, res.text)

        return {
            "id": music_id,
            "status": "pending"
        }

    finally:
        db.close()

# ================= CALLBACK =================
@app.post("/callback")
async def callback(req: Request):
    body = await req.json()

    music_id = body.get("external_id")
    audio_url = body.get("audio_url")

    if not music_id or not audio_url:
        raise HTTPException(400, "Invalid callback payload")

    db = SessionLocal()
    try:
        music = db.query(Music).filter(Music.id == music_id).first()
        if not music:
            raise HTTPException(404, "Music not found")

        music.status = "complete"
        music.audio_url = audio_url
        db.commit()

        return {"ok": True}

    finally:
        db.close()

# ================= DOWNLOAD =================
@app.get("/download/{music_id}")
def download(music_id: str):
    db = SessionLocal()
    try:
        music = db.query(Music).filter(Music.id == music_id).first()

        if not music or not music.audio_url:
            raise HTTPException(404, "Belum siap")

        r = requests.get(music.audio_url, timeout=30)
        path = f"/tmp/{music_id}.mp3"

        with open(path, "wb") as f:
            f.write(r.content)

        return FileResponse(
            path,
            media_type="audio/mpeg",
            filename=f"{music.title}.mp3"
        )

    finally:
        db.close()    return FileResponse(path, media_type="audio/mpeg", filename=f"{music.title}.mp3")

