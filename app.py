import os
import uuid
import time
import requests
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError

# ================= ENV =================
KIE_API_KEY = os.getenv("KIE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")

if not all([KIE_API_KEY, DATABASE_URL, CALLBACK_URL]):
    raise RuntimeError("ENV BELUM LENGKAP")

DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ================= DATABASE =================
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

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


# ================= FASTAPI =================
app = FastAPI(title="AI Music Generator")


@app.on_event("startup")
def startup_db():
    """Render-safe DB init"""
    for i in range(10):
        try:
            Base.metadata.create_all(bind=engine)
            print("✅ Database connected")
            return
        except OperationalError:
            print(f"⏳ DB belum siap, retry {i+1}/10")
            time.sleep(3)

    raise RuntimeError("❌ Database tidak bisa dikoneksi")


# ================= SCHEMA =================
class GenerateReq(BaseModel):
    style: str
    title: str
    prompt: str
    instrumental: bool = False


# ================= GENERATE =================
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
            status="pending",
        )

        db.add(music)
        db.commit()

        payload = {
            "style": data.style,
            "title": data.title,
            "prompt": data.prompt,
            "instrumental": data.instrumental,
            "callback_url": CALLBACK_URL,
            "external_id": music_id,
        }

        res = requests.post(
            "https://api.kie.ai/api/v1/generate/music",
            json=payload,
            headers={
                "Authorization": f"Bearer {KIE_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if res.status_code != 200:
            music.status = "failed"
            db.commit()
            raise HTTPException(500, res.text)

        return {"id": music_id, "status": "pending"}

    finally:
        db.close()


# ================= CALLBACK =================
@app.post("/callback")
async def callback(req: Request):
    body = await req.json()

    music_id = body.get("external_id") or body.get("data", {}).get("external_id")
    audio_url = body.get("audio_url") or body.get("data", {}).get("audio_url")
    status = body.get("status") or body.get("data", {}).get("status", "complete")

    if not music_id:
        raise HTTPException(400, "Invalid callback")

    db = SessionLocal()
    try:
        music = db.query(Music).filter(Music.id == music_id).first()
        if not music:
            raise HTTPException(404, "Music not found")

        if music.status == "complete":
            return {"ok": True}

        music.status = status
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

        if not music or music.status != "complete":
            raise HTTPException(404, "Belum siap")

        r = requests.get(music.audio_url, stream=True, timeout=30)
        r.raise_for_status()

        path = f"/tmp/{music_id}.mp3"
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        safe_title = "".join(c for c in music.title if c.isalnum() or c in " _-")
        return FileResponse(path, filename=f"{safe_title or music_id}.mp3")

    finally:
        db.close()


# ================= HEALTH =================
@app.get("/health")
def health():
    return {"ok": True}

# ================= HEALTH =================
@app.get("/health")
def health():
    return {"ok": True}

