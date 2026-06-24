"""Dashboard 唯讀查詢模組 — 所有 DB 讀取操作集中於此，不執行任何寫入。

欄位名稱對應 db/schema.sql 實際定義：
- agents: role / display_name / discord_user_id / bot_discord_id / reports_to
- tasks: id / title / assigner / assignee / status / deadline
- messages: id / channel_id / speaker_kind / role / text / hop / created_at
"""
from typing import Any

from core.db import get_conn


def get_tasks_overview() -> dict[str, list[dict[str, Any]]]:
    """取得任務看板資料（按狀態分組）。

    tasks.status 合法值：assigned / in_progress / done / blocked / cancelled

    Returns:
        dict，key 為狀態，value 為該狀態的任務清單
    """
    with get_conn(read_only=True) as conn:
        rows = conn.execute(
            """SELECT id, title, assignee, assigner,
                      status, priority, deadline, created_at, updated_at
               FROM tasks
               ORDER BY created_at DESC
               LIMIT 100"""
        ).fetchall()

    result: dict[str, list[dict]] = {
        "assigned": [],
        "in_progress": [],
        "done": [],
        "blocked": [],
        "cancelled": [],
    }

    for row in rows:
        status = row["status"] or "assigned"
        if status not in result:
            result[status] = []
        result[status].append(dict(row))

    return result


def get_recent_messages(limit: int = 50) -> list[dict[str, Any]]:
    """取得最近的頻道訊息。

    messages 欄位：text / role / speaker_kind / hop（非 content / sender_role / sender_type / hop_count）

    Args:
        limit: 最多回傳筆數，預設 50

    Returns:
        訊息清單
    """
    if limit > 200:
        limit = 200  # 防止過大查詢

    with get_conn(read_only=True) as conn:
        rows = conn.execute(
            """SELECT id, role, speaker_kind, text,
                      hop, created_at
               FROM messages
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_recent_notes(limit: int = 20) -> list[dict[str, Any]]:
    """取得最近的筆記。

    Args:
        limit: 最多回傳筆數

    Returns:
        筆記清單，每筆含 owner / content / tags / created_at
    """
    with get_conn(read_only=True) as conn:
        rows = conn.execute(
            """SELECT id, owner, content, tags, created_at
               FROM notes
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_agents_status() -> list[dict[str, Any]]:
    """取得所有 agent 的基本資訊。

    agents 欄位：role / display_name / discord_user_id / bot_discord_id / reports_to

    Returns:
        agents 清單
    """
    with get_conn(read_only=True) as conn:
        rows = conn.execute(
            """SELECT role, display_name, discord_user_id,
                      bot_discord_id, reports_to
               FROM agents
               ORDER BY role"""
        ).fetchall()

    return [dict(row) for row in rows]


def get_system_stats() -> dict[str, int]:
    """取得系統統計概覽（各表筆數）。

    Returns:
        包含各表記錄數的 dict
    """
    with get_conn(read_only=True) as conn:
        stats = {}
        for table in ("tasks", "messages", "notes", "meeting_records", "reflections"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = count

    return stats


if __name__ == "__main__":
    """冒煙測試（需要 DB 已初始化）。"""
    print("TC1：get_agents_status()")
    agents = get_agents_status()
    print(f"  agents: {[a['role'] for a in agents]}")
    assert isinstance(agents, list), "應回傳 list"
    print("  PASS")

    print("TC2：get_system_stats()")
    stats = get_system_stats()
    print(f"  stats: {stats}")
    assert "tasks" in stats, "應包含 tasks 統計"
    print("  PASS")

    print("TC3：get_tasks_overview()")
    overview = get_tasks_overview()
    print(f"  statuses: {list(overview.keys())}")
    assert "assigned" in overview, "應包含 assigned 狀態"
    print("  PASS")
