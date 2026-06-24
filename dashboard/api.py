"""addwii-pm Dashboard API — FastAPI，port 8092，提供任務看板與系統監控。

API 端點：
- GET /api/tasks       → 任務看板（按狀態分組）
- GET /api/messages    → 最近訊息記錄
- GET /api/notes       → 最近筆記
- GET /api/agents      → agent 清單
- GET /api/stats       → 系統統計
- GET /                → 前端 SPA index.html
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard.queries import (
    get_agents_status,
    get_recent_messages,
    get_recent_notes,
    get_system_stats,
    get_tasks_overview,
)

app = FastAPI(title="addwii-pm Dashboard", version="1.0.0")

# 靜態檔案目錄（dashboard/static/）
_STATIC_DIR = Path(__file__).resolve().parent / "static"


# ─── API 端點 ─────────────────────────────────────────────────────

@app.get("/api/tasks")
def api_tasks() -> dict:
    """回傳任務看板資料（按狀態分組）。"""
    try:
        return get_tasks_overview()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/messages")
def api_messages(limit: int = 50) -> list:
    """回傳最近的頻道訊息。

    Query params:
        limit: 最多回傳筆數（預設 50，最大 200）
    """
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit 必須在 1~200 之間")
    try:
        return get_recent_messages(limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/notes")
def api_notes(limit: int = 20) -> list:
    """回傳最近的筆記。"""
    try:
        return get_recent_notes(limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/agents")
def api_agents() -> list:
    """回傳所有 agent 資訊。"""
    try:
        return get_agents_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stats")
def api_stats() -> dict:
    """回傳系統統計概覽。"""
    try:
        return get_system_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/overview")
def api_overview() -> dict:
    """回傳 Dashboard 總覽（tasks + stats + agents）。"""
    try:
        return {
            "tasks": get_tasks_overview(),
            "stats": get_system_stats(),
            "agents": get_agents_status(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── 靜態 SPA ─────────────────────────────────────────────────────

if _STATIC_DIR.exists():
    # 掛載 /static 路徑（CSS/JS 等資源）
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
def root() -> FileResponse:
    """提供前端 SPA 的 index.html。"""
    index_file = _STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html 不存在，請確認 dashboard/static/ 目錄")
    return FileResponse(str(index_file))


# 允許 SPA 路由（回退到 index.html）
@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    """SPA 路由回退：所有非 API 路徑都回傳 index.html。"""
    # 若是 /api/ 開頭，不回退（由上方端點處理，到這裡表示 404）
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API 端點不存在")
    index_file = _STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html 不存在")
    return FileResponse(str(index_file))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8092)
