from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import requests, os, uuid

# ================= CONFIG =================
KIE_API_KEY = os.getenv("KIE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
KIE_BASE_URL = "https://api.kie.ai"
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ================= DB =================
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Music(Base):
    __tablename__ = "music"
    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    style = Column(String)
    prompt = Column(String)
    instrumental = Column(Boolean)
    file_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ================= APP =================
app = FastAPI()

class MusicRequest(BaseModel):
    style: str
    title: str
    prompt: str
    instrumental: bool = False

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/generate-music")
def generate_music(data: MusicRequest):
    if not KIE_API_KEY:
        raise HTTPException(500, "KIE_API_KEY missing")

    r = requests.post(
        f"{KIE_BASE_URL}/api/v1/generate/music",
        headers={
            "Authorization": f"Bearer {KIE_API_KEY}",
            "Content-Type": "application/json"
        },
        json=data.dict()
    )

    if r.status_code != 200:
        raise HTTPException(500, r.text)

    audio_url = r.json().get("audio_url")
    if not audio_url:
        raise HTTPException(500, "audio_url not found")

    file_id = f"{uuid.uuid4()}.mp3"
    file_path = f"{DOWNLOAD_DIR}/{file_id}"

    audio = requests.get(audio_url)
    with open(file_path, "wb") as f:
        f.write(audio.content)

    db = SessionLocal()
    db.add(Music(
        id=file_id,
        title=data.title,
        style=data.style,
        prompt=data.prompt,
        instrumental=data.instrumental,
        file_path=file_path
    ))
    db.commit()
    db.close()

    return {"download_url": f"/download/{file_id}"}

@app.get("/download/{file_id}")
def download(file_id: str):
    path = f"{DOWNLOAD_DIR}/{file_id}"
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/mpeg", filename=file_id)

@app.get("/music")
def list_music():
    db = SessionLocal()
    data = db.query(Music).order_by(Music.created_at.desc()).all()
    db.close()
    return data
