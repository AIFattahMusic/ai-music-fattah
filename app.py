import os
import uuid
import time
import requests
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, String, Boolean, DateTime, text
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
    pool_pre_ping=True,
    pool_recycle=300,
)

# ---- RETRY DB (WAJIB UNTUK RENDER) ----
for _ in range(5):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception:
        time.sleep(3)
else:
    raise RuntimeError("Gagal konek ke database setelah retry")

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


Base.metadata.create_all(bind=engine)

# ================= FASTAPI =================
app = FastAPI(title="AI Music Generator")


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
            KIE_GENERATE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {KIE_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if res.status_code != 200:
            music.status = "failed"  # FIX
            db.commit()
            raise HTTPException(status_code=500, detail=res.text)

        return {
            "id": music_id,
            "status": "pending",
        }

    finally:
        db.close()


# ================= CALLBACK =================
@app.post("/callback")
async def callback(req: Request):
    body = await req.json()

    # FIX: support flat & nested payload
    music_id = body.get("external_id") or body.get("data", {}).get("external_id")
    audio_url = body.get("audio_url") or body.get("data", {}).get("audio_url")
    status = body.get("status") or body.get("data", {}).get("status", "complete")

    if not music_id:
        raise HTTPException(status_code=400, detail="Missing external_id")

    db = SessionLocal()
    try:
        music = db.query(Music).filter(Music.id == music_id).first()
        if not music:
            raise HTTPException(status_code=404, detail="Music not found")

        # FIX: idempotent callback
        if music.status == "complete":
            return {"ok": True}

        music.status = status
        if audio_url:
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

        if not music or music.status != "complete" or not music.audio_url:
            raise HTTPException(status_code=404, detail="Belum siap")

        # FIX: stream download (hemat RAM)
        r = requests.get(music.audio_url, stream=True, timeout=30)
        r.raise_for_status()

        path = f"/tmp/{music_id}.mp3"
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        # FIX: sanitize filename
        safe_title = "".join(c for c in music.title if c.isalnum() or c in " _-")
        filename = f"{safe_title or music_id}.mp3"

        return FileResponse(
            path,
            media_type="audio/mpeg",
            filename=filename,
        )

    finally:
        db.close()


# ================= HEALTH =================
@app.get("/health")
def health():
    return {"ok": True}
