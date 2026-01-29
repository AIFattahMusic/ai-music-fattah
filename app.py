import os, json
import httpx
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

# ================= CONFIG =================
SUNO_API_KEY = os.getenv("SUNO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
BASE_URL = os.getenv("BASE_URL")

if not SUNO_API_KEY:
    raise RuntimeError("SUNO_API_KEY missing")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing")
if not BASE_URL:
    raise RuntimeError("BASE_URL missing")

SUNO_BASE = "https://api.kie.ai/api/v1"
GENERATE_URL = f"{SUNO_BASE}/generate"

app = FastAPI(
    title="AI Music Generator FULL",
    description="Generate music with Suno/Kie AI + callback + database",
    version="1.0.0"
)

# ================= DB =================
def get_db():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print("DB CONNECTION ERROR:", e)
        return None

@app.on_event("startup")
def init_db():
    db = get_db()
    if not db:
        return
    cur = db.cursor()
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
    db.commit()
    cur.close()
    db.close()

# ================= MODELS =================
class GenerateRequest(BaseModel):
    prompt: str
    style: str | None = None
    title: str | None = None
    instrumental: bool = False

# ================= ROOT =================
@app.get("/")
def root():
    return {
        "flow": "POST /generate → Suno → POST /callback → DB → download",
        "endpoints": {
            "generate": "POST /generate",
            "callback": "POST /callback",
            "status": "GET /status/{task_id}",
            "list": "GET /tasks",
            "download": "GET /download/{task_id}"
        }
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# ================= GENERATE =================
@app.post("/generate")
async def generate(req: GenerateRequest):
    headers = {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "prompt": req.prompt,
        "style": req.style or "",
        "title": req.title or "",
        "instrumental": req.instrumental,
        "customMode": True,
        "model": "V4_5",
        # ⬇️ INI YANG MEMASANG CALLBACK
        "callBackUrl": f"{BASE_URL}/callback"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(GENERATE_URL, headers=headers, json=payload)

    data = r.json()
    if "taskId" not in data:
        raise HTTPException(500, data)

    # simpan awal ke DB
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute("""
            INSERT INTO music_tasks (task_id, status, raw)
            VALUES (%s,%s,%s)
            ON CONFLICT (task_id) DO NOTHING
        """, (
            data["taskId"],
            data.get("status", "submitted"),
            json.dumps(data)
        ))
        db.commit()
        cur.close()
        db.close()

    return data

# ================= CALLBACK (INI YANG KAMU CARI) =================
@app.post("/callback")
async def callback(request: Request):
    data = await request.json()
    print("CALLBACK MASUK:", data)

    task_id = data.get("taskId")
    if not task_id:
        return {"status": "ignored"}

    db = get_db()
    if not db:
        return {"status": "db_error"}

    cur = db.cursor()
    cur.execute("""
        INSERT INTO music_tasks (task_id, status, audio_url, raw)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (task_id)
        DO UPDATE SET
            status=EXCLUDED.status,
            audio_url=EXCLUDED.audio_url,
            raw=EXCLUDED.raw
    """, (
        task_id,
        data.get("status"),
        data.get("audioUrl"),
        json.dumps(data)
    ))
    db.commit()
    cur.close()
    db.close()

    return {"status": "saved", "task_id": task_id}

# ================= STATUS =================
@app.get("/status/{task_id}")
def status(task_id: str):
    db = get_db()
    if not db:
        raise HTTPException(500, "DB error")

    cur = db.cursor()
    cur.execute("""
        SELECT task_id, status, audio_url, created_at
        FROM music_tasks WHERE task_id=%s
    """, (task_id,))
    row = cur.fetchone()
    cur.close()
    db.close()

    if not row:
        raise HTTPException(404, "Task not found")

    return row

# ================= LIST =================
@app.get("/tasks")
def tasks():
    db = get_db()
    if not db:
        raise HTTPException(500, "DB error")

    cur = db.cursor()
    cur.execute("""
        SELECT task_id, status, audio_url, created_at
        FROM music_tasks
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows

# ================= DOWNLOAD =================
@app.get("/download/{task_id}")
def download(task_id: str):
    db = get_db()
    if not db:
        raise HTTPException(500, "DB error")

    cur = db.cursor()
    cur.execute("""
        SELECT audio_url FROM music_tasks WHERE task_id=%s
    """, (task_id,))
    row = cur.fetchone()
    cur.close()
    db.close()

    if not row or not row["audio_url"]:
        raise HTTPException(404, "Audio not ready")

    return {"download_url": row["audio_url"]}
