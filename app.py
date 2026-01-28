# app.py — FULL, LENGKAP, TERISI SEMUA
# FastAPI + KIE.AI + Callback + PostgreSQL(Render) + Download

import os
import uuid
import requests
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

# ===================== ENV =====================
KIE_API_KEY = os.getenv("KIE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")

if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY belum di-set")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL belum di-set")
if not CALLBACK_URL:
    raise RuntimeError("CALLBACK_URL belum di-set")

# ===================== KIE.AI URL =====================
"KIE_GENERATE_URL = "https://api.kie.ai/api/v1/generate/music""

# ===================== DATABASE =====================
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"},
    pool_pre_ping=True
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
    status = Column(String)            # pending / complete
    audio_url = Column(String)         # diisi via callback
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ===================== FASTAPI =====================
app = FastAPI(title="KIE.AI Music Generator FULL")

# ===================== SCHEMA =====================
class GenerateRequest(BaseModel):
    style: str
    title: str
    prompt: str
    instrumental: bool = False

# ===================== ROOT =====================
@app.get("/")
def root():
    return {"status": "ok"}

# ===================== GENERATE =====================
@app.post("/generate-music")
def generate_music(data: GenerateRequest):
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }

    music_id = str(uuid.uuid4())

    payload = {
        "style": data.style,
        "title": data.title,
        "prompt": data.prompt,
        "instrumental": data.instrumental,
        "callBackUrl": CALLBACK_URL,
        "externalId": music_id
    }

    r = requests.post(KIE_GENERATE_URL, json=payload, headers=headers, timeout=120)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)

    db = SessionLocal()
    db.add(Music(
        id=music_id,
        title=data.title,
        style=data.style,
        prompt=data.prompt,
        instrumental=data.instrumental,
        status="pending"
    ))
    db.commit()
    db.close()

    return {"id": music_id, "status": "pending"}

# ===================== CALLBACK =====================
@app.post("/callback")
async def callback(request: Request):
    payload = await request.json()

    music_id = payload.get("externalId")
    audio_url = payload.get("audio_url")

    if not music_id or not audio_url:
        return {"ignored": True}

    db = SessionLocal()
    music = db.query(Music).filter(Music.id == music_id).first()
    if not music:
        db.close()
        return {"error": "not found"}

    music.status = "complete"
    music.audio_url = audio_url
    db.commit()
    db.close()

    return {"status": "saved", "id": music_id}

# ===================== DOWNLOAD =====================
@app.get("/download/{music_id}")
def download(music_id: str):
    db = SessionLocal()
    music = db.query(Music).filter(Music.id == music_id).first()
    db.close()

    if not music or not music.audio_url:
        raise HTTPException(status_code=404, detail="Audio belum siap")

    filename = f"{music_id}.mp3"
    filepath = f"/tmp/{filename}"

    r = requests.get(music.audio_url, timeout=120)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Download gagal")

    with open(filepath, "wb") as f:
        f.write(r.content)

    return FileResponse(filepath, media_type="audio/mpeg", filename=filename)

# ===================== LIST DB =====================
@app.get("/music")
def list_music():
    db = SessionLocal()
    data = db.query(Music).order_by(Music.created_at.desc()).all()
    db.close()
    return data

