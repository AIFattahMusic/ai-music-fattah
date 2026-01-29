import os, json
import httpx
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from psycopg2.extras import RealDictCursor

# ================= CONFIG =================
SUNO_API_KEY = os.getenv("SUNO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CALLBACK_URL = os.getenv("CALLBACK_URL")  # FIXED PUBLIC URL

if not SUNO_API_KEY:
    raise RuntimeError("SUNO_API_KEY missing")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing")
if not CALLBACK_URL:
    raise RuntimeError("CALLBACK_URL missing")

SUNO_BASE = "https://api.kie.ai/api/v1"
GENERATE_URL = f"{SUNO_BASE}/generate"

app = FastAPI(title="AI Music FULL API", version="FINAL")

# ================= DB =================
def db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.on_event("startup")
def init_db():
    c = db()
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS music_tasks (
            id SERIAL PRIMARY KEY,
            task_id TEXT UNIQUE,
            status TEXT,
            audio_url TEXT,
            raw JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    c.commit()
    cur.close()
    c.close()

# ================= ROOT =================
@app.get("/")
def root():
    return {
        "service": "AI Music FULL",
        "flow": "generate → callback → database → download",
        "endpoints": [
            "/generate",
            "/callback",
            "/tasks",
            "/download/{task_id}",
            "/db-check"
        ]
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# ================= GENERATE =================
@app.post("/generate")
async def generate(req: dict):
    body = {
        "prompt": req.get("prompt"),
        "style": req.get("style"),
        "title": req.get("title"),
        "instrumental": req.get("instrumental", False),
        "customMode": True,
        "model": "V4_5",
        "callBackUrl": CALLBACK_URL
    }

    headers = {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(GENERATE_URL, headers=headers, json=body)

    return r.json()

# ================= CALLBACK =================
@app.post("/callback")
async def callback(request: Request):
    data = await request.json()
    task_id = data.get("taskId")

    if not task_id:
        return {"status": "ignored"}

    c = db()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO music_tasks (task_id, status, audio_url, raw)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (task_id)
        DO UPDATE SET
            status=EXCLUDED.status,
            audio_url=EXCLUDED.audio_url,
            raw=EXCLUDED.raw;
    """, (
        task_id,
        data.get("status"),
        data.get("audioUrl"),
        json.dumps(data)
    ))
    c.commit()
    cur.close()
    c.close()

    return {"status": "saved", "task_id": task_id}

# ================= DATA =================
@app.get("/tasks")
def tasks():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM music_tasks ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    c.close()
    return rows

@app.get("/download/{task_id}")
def download(task_id: str):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT audio_url FROM music_tasks WHERE task_id=%s", (task_id,))
    row = cur.fetchone()
    cur.close()
    c.close()

    if not row or not row["audio_url"]:
        raise HTTPException(404, "Audio not ready")

    return {
        "task_id": task_id,
        "download_url": row["audio_url"]
    }

@app.get("/db-check")
def db_check():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM music_tasks")
    total = cur.fetchone()["total"]
    cur.close()
    c.close()

    return {
        "database": "connected",
        "total_records": total
    }
