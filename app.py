import os
import json
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from psycopg2.extras import RealDictCursor

# =====================================================
# CONFIG
# =====================================================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app = FastAPI(
    title="AI Music Database API",
    version="1.0.0"
)

# =====================================================
# DATABASE CONNECTION
# =====================================================
def get_conn():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )

# =====================================================
# INIT TABLE (AUTO CREATE)
# =====================================================
@app.on_event("startup")
def init_db():
    conn = get_conn()
    cur = conn.cursor()
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
    conn.commit()
    cur.close()
    conn.close()

# =====================================================
# HEALTH CHECK
# =====================================================
@app.get("/health")
def health():
    return {"status": "ok"}

# =====================================================
# SAVE CALLBACK DATA (DARI API GENERATE)
# =====================================================
@app.post("/save")
async def save_task(request: Request):
    data = await request.json()

    task_id = data.get("taskId")
    status = data.get("status")
    audio_url = data.get("audioUrl")

    if not task_id:
        raise HTTPException(status_code=400, detail="taskId is required")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO music_tasks (task_id, status, audio_url, raw)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (task_id)
        DO UPDATE SET
            status = EXCLUDED.status,
            audio_url = EXCLUDED.audio_url,
            raw = EXCLUDED.raw;
    """, (
        task_id,
        status,
        audio_url,
        json.dumps(data)
    ))

    conn.commit()
    cur.close()
    conn.close()

    return {
        "status": "saved",
        "taskId": task_id
    }

# =====================================================
# GET ALL TASKS (UNTUK ANDROID / ADMIN)
# =====================================================
@app.get("/tasks")
def get_tasks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM music_tasks
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# =====================================================
# GET TASK BY ID
# =====================================================
@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM music_tasks
        WHERE task_id = %s
    """, (task_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    return row
