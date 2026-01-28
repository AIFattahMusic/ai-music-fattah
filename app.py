import os
import json
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base

# =====================================================
# ENV
# =====================================================
KIE_API_KEY = os.getenv("KIE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY tidak ada")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL tidak ada")

# =====================================================
# FIX DATABASE URL (RENDER BUG FIX)
# =====================================================
# Render sering kasih: postgres://
# SQLAlchemy butuh: postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# =====================================================
# DATABASE (POSTGRESQL + SSL)
# =====================================================
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"},
    pool_pre_ping=True
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class MusicTask(Base):
    __tablename__ = "music_tasks"

    id = Column(Integer, primary_key=True)
    task_id = Column(String, unique=True, index=True)
    status = Column(String)
    payload = Column(Text)

Base.metadata.create_all(bind=engine)

# =====================================================
# KIE.AI CONFIG (ENDPOINT BENAR)
# =====================================================
KIE_GENERATE_URL = "https://api.kie.ai/api/v1/suno/generate/music"

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
        "database": "Render PostgreSQL (fixed)"
    }

# =====================================================
# REQUEST MODEL
# =====================================================
class GenerateMusic(BaseModel):
    style: str
    title: str
    prompt: str
    instrumental: bool = False  # ADA VOKAL

# =====================================================
# GENERATE MUSIC + SAVE DATABASE
# =====================================================
@app.post("/generate-music")
async def generate_music(req: GenerateMusic):
    payload = {
        "model": "V4_5",
        "style": req.style,
        "title": req.title,
        "prompt": req.prompt,
        "customMode": True,
        "instrumental": False
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            KIE_GENERATE_URL,
            headers=HEADERS,
            json=payload
        )

    if r.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail={
                "kie_status": r.status_code,
                "kie_response": r.text
            }
        )

    task_id = r.json()["data"]["taskId"]

    db = SessionLocal()
    db.add(
        MusicTask(
            task_id=task_id,
            status="submitted",
            payload=json.dumps(payload)
        )
    )
    db.commit()
    db.close()

    return {
        "task_id": task_id,
        "saved_to_database": True
    }

# =====================================================
# LIST TASKS (CEK DATABASE)
# =====================================================
@app.get("/tasks")
def list_tasks():
    db = SessionLocal()
    tasks = db.query(MusicTask).all()
    db.close()

    return [
        {
            "task_id": t.task_id,
            "status": t.status
        }
        for t in tasks
    ]
