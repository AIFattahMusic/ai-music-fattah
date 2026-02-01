‎import os
‎import httpx
‎import requests
‎import psycopg2
‎from fastapi import FastAPI, Request, HTTPException
‎from fastapi.staticfiles import StaticFiles
‎from pydantic import BaseModel
‎from typing import Optional
‎
‎# ==================================================
‎# WAJIB PALING ATAS: BUAT FOLDER MEDIA
‎# ==================================================
‎os.makedirs("media", exist_ok=True)
‎
‎# ================= ENV =================
‎SUNO_API_KEY = os.getenv("SUNO_API_KEY")
‎
‎BASE_URL = os.getenv(
‎    "BASE_URL",
‎    "https://ai-music-fattah.onrender.com"
‎)
‎
‎CALLBACK_URL = f"{BASE_URL}/callback"
‎
‎SUNO_BASE_API = "https://api.kie.ai/api/v1"
‎STYLE_GENERATE_URL = f"{SUNO_BASE_API}/style/generate"
‎MUSIC_GENERATE_URL = f"{SUNO_BASE_API}/generate"
‎STATUS_URL = f"{SUNO_BASE_API}/generate/record-info"
‎
‎# ================= APP =================
‎app = FastAPI(
‎    title="AI Music Suno API Wrapper",
‎    version="1.0.3"
‎)
‎
‎# ==================================================
‎# STATIC FILES
‎# ==================================================
‎app.mount("/media", StaticFiles(directory="media"), name="media")
‎
‎# ================= REQUEST MODEL =================
‎class BoostStyleRequest(BaseModel):
‎    content: str
‎
‎class GenerateMusicRequest(BaseModel):
‎    prompt: str
‎    style: Optional[str] = None
‎    title: Optional[str] = None
‎    instrumental: bool = False
‎    customMode: bool = False
‎    model: str = "V4_5"
‎
‎# ================= HELPERS =================
‎def suno_headers():
‎    if not SUNO_API_KEY:
‎        raise HTTPException(
‎            status_code=500,
‎            detail="SUNO_API_KEY not set in environment"
‎        )
‎    return {
‎        "Authorization": f"Bearer {SUNO_API_KEY}",
‎        "Content-Type": "application/json"
‎    }
‎
‎def normalize_model(model: str) -> str:
‎    if model.lower() in ["v4", "v4_5", "v45"]:
‎        return "V4_5"
‎    return model
‎
‎# ================= ENDPOINTS =================
‎@app.get("/")
‎def root():
‎    return {"status": "running", "service": "AI Music Suno API"}
‎
‎@app.get("/health")
‎def health():
‎    return {"status": "ok"}
‎
‎@app.post("/boost-style")
‎async def boost_style(payload: BoostStyleRequest):
‎    async with httpx.AsyncClient(timeout=60) as client:
‎        res = await client.post(
‎            STYLE_GENERATE_URL,
‎            headers=suno_headers(),
‎            json={"content": payload.content}
‎        )
‎    return res.json()
‎
‎@app.post("/generate-music")
‎async def generate_music(payload: GenerateMusicRequest):
‎    body = {
‎        "prompt": payload.prompt,
‎        "customMode": payload.customMode,
‎        "instrumental": payload.instrumental,
‎        "model": normalize_model(payload.model),
‎        "callBackUrl": CALLBACK_URL
‎    }
‎
‎    if payload.style:
‎        body["style"] = payload.style
‎    if payload.title:
‎        body["title"] = payload.title
‎
‎    async with httpx.AsyncClient(timeout=60) as client:
‎        res = await client.post(
‎            MUSIC_GENERATE_URL,
‎            headers=suno_headers(),
‎            json=body
‎        )
‎
‎    if res.status_code != 200:
‎        print("SUNO GENERATE ERROR:", res.text)
‎        raise HTTPException(status_code=500, detail="Gagal generate musik")
‎
‎    return res.json()
‎
‎@app.get("/record-info/{task_id}")
‎async def record_info(task_id: str):
‎    async with httpx.AsyncClient(timeout=30) as client:
‎        res = await client.get(
‎            STATUS_URL,
‎            headers=suno_headers(),
‎            params={"taskId": task_id}
‎        )
‎    return res.json()
‎
‎@app.post("/callback")
‎async def callback(request: Request):
‎    data = await request.json()
‎
‎    try:
‎        task_id = data.get("taskId") or data.get("task_id")
‎
‎        items = data.get("data") or []
‎        if not items:
‎            return {"status": "ignored"}
‎
‎        item = items[0]
‎
‎        state = item.get("state") or item.get("status")
‎        if state != "succeeded":
‎            return {"status": "processing"}
‎
‎        audio_url = (
‎            item.get("audio_url")
‎            or item.get("audioUrl")
‎            or item.get("audio")
‎            or item.get("streamAudioUrl")
‎        )
‎
‎        image_url = item.get("imageUrl")
‎        lyrics = item.get("lyrics")
‎        title = item.get("title", "Untitled")
‎
‎        if not audio_url:
‎            return {"status": "no_audio"}
‎
‎        # === SAVE MP3 ===
‎        audio_bytes = requests.get(audio_url).content
‎        file_path = f"media/{task_id}.mp3"
‎
‎        with open(file_path, "wb") as f:
‎            f.write(audio_bytes)
‎
‎        local_audio_url = f"{BASE_URL}/media/{task_id}.mp3"
‎
‎        # === INSERT DB ===
‎        conn = psycopg2.connect(os.environ["DATABASE_URL"])
‎        cur = conn.cursor()
‎
‎        cur.execute("""
‎            INSERT INTO songs (task_id, title, audio_url, cover_url, lyrics, status)
‎            VALUES (%s, %s, %s, %s, %s, %s)
‎            ON CONFLICT (task_id) DO NOTHING
‎        """, (
‎            task_id,
‎            title,
‎            local_audio_url,
‎            image_url,
‎            lyrics,
‎            "done"
‎        ))
‎
‎        conn.commit()
‎        cur.close()
‎        conn.close()
‎
‎        return {"status": "saved"}
‎
‎    except Exception as e:
‎        return {"status": "error", "error": str(e)}
‎
‎‎# ================= DB TEST =================
‎def get_conn():
‎    return psycopg2.connect(os.environ["DATABASE_URL"])
‎
‎@app.get("/db-all")
‎def db_all():
‎    conn = get_conn()
‎    cur = conn.cursor()
‎    cur.execute("""
‎        SELECT *
‎        FROM information_schema.tables
‎        WHERE table_schema = 'public';
‎    """)
‎    rows = cur.fetchall()
‎    cur.close()
‎    conn.close()
‎    return rows
‎

