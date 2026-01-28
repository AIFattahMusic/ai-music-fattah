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

# --- Load env ---
load_dotenv()
API_KEY = os.getenv("SUNO_API_KEY")
CALLBACK_URL = os.getenv("CALLBACK_URL")

# --- Database setup ---
DATABASE_URL = "sqlite:///./music_tasks.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database model ---
class MusicTask(Base):
    __tablename__ = "music_tasks"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True)
    status = Column(String, nullable=True)
    audio_urls = Column(Text, nullable=True)   # JSON array
    saved_files = Column(Text, nullable=True)  # JSON array

Base.metadata.create_all(bind=engine)

# --- App instance ---
app = FastAPI()

# --- Suno/KIE API endpoints ---
BOOST_STYLE_URL = "https://api.kie.ai/api/v1/style/generate"
GENERATE_MUSIC_URL = "https://api.kie.ai/api/v1/generate/music"
TASK_DETAIL_URL = "https://api.kie.ai/api/v1/music/record-info"

# --- Request body models ---
class BoostStyleRequest(BaseModel):
    content: str

class MusicGenerateRequest(BaseModel):
    style: str
    title: str
    prompt: str = ""
    customMode: bool = True
    instrumental: bool = True

# --- Dependency: DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Boost style endpoint ---
@app.post("/boost-style")
async def boost_style(req: BoostStyleRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key missing")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"content": req.content}

    async with httpx.AsyncClient() as client:
        resp = await client.post(BOOST_STYLE_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    boosted = data.get("data", {}).get("result")
    return {"boosted_style": boosted}

# --- Generate music endpoint ---
@app.post("/generate-music")
async def generate_music(req: MusicGenerateRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key missing")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "V4_5",
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

    # save task in db
    db = next(get_db())
    new_task = MusicTask(task_id=task_id, status="submitted", audio_urls="[]", saved_files="[]")
    db.add(new_task)
    db.commit()

    return {"task_id": task_id, "status": "submitted"}

# --- Poll task status + save + download ---
@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key missing")

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
    audio_urls = info.get("data", {}).get("audioUrls", [])
    saved_list = []

    # save downloaded files if complete
    if status == "complete" and audio_urls:
        for url in audio_urls:
            r = await client.get(url)
            fname = f"audio_output/{uuid.uuid4()}.mp3"
            os.makedirs(os.path.dirname(fname), exist_ok=True)
            with open(fname, "wb") as f:
                f.write(r.content)
            saved_list.append(fname)

    # update db record
    task.status = status
    task.audio_urls = json.dumps(audio_urls)
    task.saved_files = json.dumps(saved_list)
    db.commit()

    return {"status": status, "audioUrls": audio_urls, "downloaded_files": saved_list}

# --- Callback webhook ---
@app.post("/callback")
async def callback_handler(request: Request):
    payload = await request.json()
    task_id = payload.get("data", {}).get("taskId")
    audio_urls = payload.get("data", {}).get("audioUrls", [])

    db = next(get_db())
    task = db.query(MusicTask).filter(MusicTask.task_id == task_id).first()
    if not task:
        # if no db entry yet, create
        task = MusicTask(task_id=task_id, status="complete")
        db.add(task)

    saved_list = []
    async with httpx.AsyncClient() as client:
        for url in audio_urls:
            r = await client.get(url)
            fname = f"audio_output/{uuid.uuid4()}.mp3"
            os.makedirs(os.path.dirname(fname), exist_ok=True)
            with open(fname, "wb") as f:
                f.write(r.content)
            saved_list.append(fname)

    task.status = "complete"
    task.audio_urls = json.dumps(audio_urls)
    task.saved_files = json.dumps(saved_list)
    db.commit()

    return {"status":"ok", "saved_files": saved_list}
