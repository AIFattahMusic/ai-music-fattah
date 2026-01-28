import os
import uuid
import json
import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load env local (optional — Render reads env vars natively)
load_dotenv()

API_KEY = os.getenv("SUNO_API_KEY")
CALLBACK_URL = os.getenv("CALLBACK_URL")

# Validate critical config
if not API_KEY:
    raise Exception("SUNO_API_KEY is required")

app = FastAPI()

# -----------------------------
# DATABASE SETUP (SQLite + SQLAlchemy)
# -----------------------------
DATABASE_URL = "sqlite:///./music_tasks.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class MusicTask(Base):
    __tablename__ = "music_tasks"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True)
    status = Column(String, nullable=True)
    audio_urls = Column(Text, nullable=True)
    saved_files = Column(Text, nullable=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------
# SUNO/KIE API ENDPOINTS
# -----------------------------
BOOST_STYLE_URL = "https://api.kie.ai/api/v1/style/generate"
GENERATE_MUSIC_URL = "https://api.kie.ai/api/v1/generate/music"
TASK_DETAIL_URL = "https://api.kie.ai/api/v1/music/record-info"

# -----------------------------
# REQUEST MODELS
# -----------------------------
class BoostStyleRequest(BaseModel):
    content: str

class MusicGenerateRequest(BaseModel):
    style: str
    title: str
    prompt: str = ""
    customMode: bool = True
    instrumental: bool = True

# -----------------------------
# 1) ROOT / HEALTH CHECK
# -----------------------------
@app.get("/")
def home():
    return {"message": "FastAPI is running"}

# -----------------------------
# 2) BOOST STYLE
# -----------------------------
@app.post("/boost-style")
async def boost_style(req: BoostStyleRequest):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"content": req.content}
    async with httpx.AsyncClient() as client:
        res = await client.post(BOOST_STYLE_URL, headers=headers, json=payload)
        res.raise_for_status()
        data = res.json()
    boosted = data.get("data", {}).get("result")
    return {"boosted_style": boosted}

# -----------------------------
# 3) GENERATE MUSIC
# -----------------------------
@app.post("/generate-music")
async def generate_music(req: MusicGenerateRequest):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "V4_5",  # pakai model V4_5
        "style": req.style,
        "title": req.title,
        "prompt": req.prompt,
        "customMode": req.customMode,
        "instrumental": req.instrumental,
        "callBackUrl": CALLBACK_URL
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(GENERATE_MUSIC_URL, headers=headers, json=payload)
        res.raise_for_status()
        data = res.json()

    task_id = data.get("data", {}).get("taskId")
    db = next(get_db())
    db.add(MusicTask(task_id=task_id, status="submitted"))
    db.commit()

    return {"task_id": task_id, "status": "submitted"}

# -----------------------------
# 4) POLL TASK STATUS + DOWNLOAD
# -----------------------------
@app.get("/task-status/{task_id}")
async def task_status(task_id: str):
    db = next(get_db())
    task = db.query(MusicTask).filter(MusicTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{TASK_DETAIL_URL}?taskId={task_id}", headers=headers)
        res.raise_for_status()
        info = res.json()

    status = info.get("data", {}).get("status")
    urls  = info.get("data", {}).get("audioUrls", [])
    saved = []

    if status == "complete" and urls:
        async with httpx.AsyncClient() as client:
            for u in urls:
                audio_resp = await client.get(u)
                fname = f"audio_output/{uuid.uuid4()}.mp3"
                os.makedirs(os.path.dirname(fname), exist_ok=True)
                with open(fname, "wb") as f:
                    f.write(audio_resp.content)
                saved.append(fname)

    # Save back to DB
    task.status = status
    task.audio_urls = json.dumps(urls)
    task.saved_files = json.dumps(saved)
    db.commit()

    return {"status": status, "audioUrls": urls, "saved_files": saved}

# -----------------------------
# 5) CALLBACK WEBHOOK
# -----------------------------
@app.post("/callback")
async def callback_handler(request: Request):
    payload = await request.json()
    task_id = payload.get("data", {}).get("taskId")
    urls    = payload.get("data", {}).get("audioUrls", [])

    db = next(get_db())
    task = db.query(MusicTask).filter(MusicTask.task_id == task_id).first()
    if not task:
        task = MusicTask(task_id=task_id)

    saved = []
    async with httpx.AsyncClient() as client:
        for u in urls:
            audio_resp = await client.get(u)
            fname = f"audio_output/{uuid.uuid4()}.mp3"
            os.makedirs(os.path.dirname(fname), exist_ok=True)
            with open(fname, "wb") as f:
                f.write(audio_resp.content)
            saved.append(fname)

    task.status = "complete"
    task.audio_urls = json.dumps(urls)
    task.saved_files = json.dumps(saved)
    db.commit()

    return {"status": "ok", "saved_files": saved}
