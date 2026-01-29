import os, json, asyncio
import httpx
import psycopg2
from fastapi import FastAPI, BackgroundTasks, HTTPException
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

# ================= CONFIG =================
SUNO_API_KEY = os.getenv("SUNO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not SUNO_API_KEY or not DATABASE_URL:
    raise RuntimeError("SUNO_API_KEY dan DATABASE_URL wajib ada")

SUNO_BASE = "https://api.kie.ai/api/v1"
GENERATE_URL = f"{SUNO_BASE}/generate"
RECORD_URL = f"{SUNO_BASE}/generate/record-info"

app = FastAPI(
    title="AI Music Generator FULL",
    description="Generate musik AI + status + download (production ready)",
    version="1.0.0"
)

# ================= DB =================
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.on_event("startup")
def init_db():
    c = get_db()
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

# ================= MODEL (INI BIAR OPSI MUNCUL) =================
class GenerateMusicRequest(BaseModel):
    prompt: str
    style: str | None = None
    title: str | None = None
    instrumental: bool = False

# ================= BACKGROUND POLLING =================
async def poll_task(task_id: str):
    headers = {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

    for _ in range(40):  # ±4 menit
        await asyncio.sleep(6)
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                RECORD_URL,
                headers=headers,
                params={"taskId": task_id}
            )

        data = r.json()
        if data.get("status") in ("completed", "failed"):
            c = get_db()
            cur = c.cursor()
            cur.execute("""
                UPDATE music_tasks
                SET status=%s, audio_url=%s, raw=%s
                WHERE task_id=%s
            """, (
                data.get("status"),
                data.get("audioUrl"),
                json.dumps(data),
                task_id
            ))
            c.commit()
            cur.close()
            c.close()
            break

# ================= ROOT =================
@app.get("/")
def root():
    return {
        "flow": "POST /generate → background polling → DB → download",
        "endpoints": {
            "generate": "POST /generate",
            "status": "GET /status/{task_id}",
            "download": "GET /download/{task_id}",
            "list": "GET /tasks"
        }
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# ================= GENERATE =================
@app.post("/generate")
async def generate(req: GenerateMusicRequest, bg: BackgroundTasks):
    headers = {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "prompt": req.prompt,
        "style": req.style or "",
        "title": req.title or "",
        "instrumental": req.instrumental,
        "customMode": True,
        "model": "V4_5"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(GENERATE_URL, headers=headers, json=body)
        data = r.json()

    task_id = data.get("taskId")
    if not task_id:
        raise HTTPException(500, data)

    # simpan awal
    c = get_db()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO music_tasks (task_id, status)
        VALUES (%s,%s)
        ON CONFLICT (task_id) DO NOTHING
    """, (task_id, "processing"))
    c.commit()
    cur.close()
    c.close()

    # polling di background
    bg.add_task(poll_task, task_id)

    return {
        "task_id": task_id,
        "status": "processing"
    }

# ================= STATUS =================
@app.get("/status/{task_id}")
def status(task_id: str):
    c = get_db()
    cur = c.cursor()
    cur.execute("""
        SELECT task_id, status, audio_url, created_at
        FROM music_tasks WHERE task_id=%s
    """, (task_id,))
    row = cur.fetchone()
    cur.close()
    c.close()

    if not row:
        raise HTTPException(404, "task tidak ditemukan")

    return row

# ================= DOWNLOAD =================
@app.get("/download/{task_id}")
def download(task_id: str):
    c = get_db()
    cur = c.cursor()
    cur.execute("""
        SELECT audio_url FROM music_tasks WHERE task_id=%s
    """, (task_id,))
    row = cur.fetchone()
    cur.close()
    c.close()

    if not row or not row["audio_url"]:
        raise HTTPException(404, "audio belum siap")

    return {
        "download_url": row["audio_url"]
    }

# ================= LIST =================
@app.get("/tasks")
def tasks():
    c = get_db()
    cur = c.cursor()
    cur.execute("""
        SELECT task_id, status, created_at
        FROM music_tasks ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    c.close()
    return rows
