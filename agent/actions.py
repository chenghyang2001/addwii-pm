"""ActionHandler — 根據 ParsedAction 執行 DB 寫入，並組合 Discord 回應訊息。

所有寫入使用參數化查詢，不直接插入字串（防 SQL injection）。
"""
import datetime
from typing import Optional

from core.db import execute_write, get_conn
from core.logger import setup_logger
from agent.intent_engine import (
    ActionAssignTask,
    ActionReportTask,
    ActionAddNote,
    ActionAddMeeting,
    ActionAddReflection,
    ActionNone,
    ParsedAction,
)

_logger = setup_logger("actions")


def _now_iso() -> str:
    """回傳目前 UTC 時間的 ISO 8601 字串。"""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def handle_action(
    action: ParsedAction,
    author_role: str,
    channel_id: str,
    hop: int = 0,
) -> Optional[str]:
    """根據 ParsedAction 執行 DB 寫入，回傳 Discord 回應訊息。

    Args:
        action: IntentEngine 解析後的 Action 物件
        author_role: 發訊息的 bot 或人類的 role（'A'/'B'/'C'）
        channel_id: Discord channel ID（字串）
        hop: 目前的 hop 計數，用於 bot-to-bot [hop:N] 標記

    Returns:
        要發送到 Discord 的字串，None 表示不需要發送額外訊息
    """
    if isinstance(action, ActionAssignTask):
        return _handle_assign_task(action, author_role, hop)

    if isinstance(action, ActionReportTask):
        return _handle_report_task(action, author_role, hop)

    if isinstance(action, ActionAddNote):
        return _handle_add_note(action, author_role, hop)

    if isinstance(action, ActionAddMeeting):
        return _handle_add_meeting(action, author_role, hop)

    if isinstance(action, ActionAddReflection):
        return _handle_add_reflection(action, author_role, hop)

    # ActionNone 或未知 → 不寫 DB，由 claude_cli 純對話回應
    return None


def _handle_assign_task(
    action: ActionAssignTask, author_role: str, hop: int
) -> str:
    """指派任務到 tasks 表，並建立 task_events 記錄。"""
    now = _now_iso()
    try:
        # 插入任務
        row_id = execute_write(
            """INSERT INTO tasks
               (title, assignee_role, assigner_role, status, deadline, created_at, updated_at)
               VALUES (?, ?, ?, 'open', ?, ?, ?)""",
            (action.title, action.assignee, author_role, action.deadline, now, now),
        )
        # 記錄 task_event
        execute_write(
            """INSERT INTO task_events (task_id, actor_role, event_type, detail, created_at)
               VALUES (?, ?, 'created', ?, ?)""",
            (row_id, author_role, f"由 {author_role} 指派給 {action.assignee}", now),
        )
        deadline_str = action.deadline or "未設定"
        return (
            f"✅ 任務 #{row_id} 已指派給 {action.assignee}：{action.title}"
            f"（期限：{deadline_str}）[hop:{hop}]"
        )
    except Exception as exc:
        _logger.error("assign_task DB 寫入失敗：%s", exc)
        return f"❌ 指派任務失敗：{exc} [hop:{hop}]"


def _handle_report_task(
    action: ActionReportTask, author_role: str, hop: int
) -> str:
    """更新 tasks.status，並建立 task_events 記錄。"""
    now = _now_iso()
    try:
        # 確認任務存在
        with get_conn(read_only=True) as conn:
            row = conn.execute(
                "SELECT id, title, status FROM tasks WHERE id = ?",
                (action.task_id,),
            ).fetchone()
        if row is None:
            return f"❌ 任務 #{action.task_id} 不存在 [hop:{hop}]"

        # 更新狀態
        execute_write(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (action.status, now, action.task_id),
        )
        # 記錄 task_event
        summary = action.summary or ""
        execute_write(
            """INSERT INTO task_events (task_id, actor_role, event_type, detail, created_at)
               VALUES (?, ?, 'status_changed', ?, ?)""",
            (action.task_id, author_role, f"狀態更新為 {action.status}：{summary}", now),
        )
        status_emoji = {"open": "📋", "in_progress": "🔄", "done": "✅", "cancelled": "❌"}.get(
            action.status, "❓"
        )
        return (
            f"{status_emoji} 任務 #{action.task_id}「{row['title']}」"
            f"更新為 {action.status} [hop:{hop}]"
        )
    except Exception as exc:
        _logger.error("report_task DB 寫入失敗：%s", exc)
        return f"❌ 更新任務狀態失敗：{exc} [hop:{hop}]"


def _handle_add_note(
    action: ActionAddNote, author_role: str, hop: int
) -> str:
    """新增筆記到 notes 表。"""
    now = _now_iso()
    try:
        row_id = execute_write(
            "INSERT INTO notes (owner, content, created_at) VALUES (?, ?, ?)",
            (author_role, action.text, now),
        )
        return f"📝 筆記 #{row_id} 已儲存 [hop:{hop}]"
    except Exception as exc:
        _logger.error("add_note DB 寫入失敗：%s", exc)
        return f"❌ 儲存筆記失敗：{exc} [hop:{hop}]"


def _handle_add_meeting(
    action: ActionAddMeeting, author_role: str, hop: int
) -> str:
    """新增會議記錄到 meeting_records 表。"""
    now = _now_iso()
    try:
        row_id = execute_write(
            """INSERT INTO meeting_records
               (title, recorder_role, decisions, action_items, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (action.title, author_role, action.decisions, action.action_items, now),
        )
        return f"🗒️ 會議記錄 #{row_id}「{action.title}」已儲存 [hop:{hop}]"
    except Exception as exc:
        _logger.error("add_meeting DB 寫入失敗：%s", exc)
        return f"❌ 儲存會議記錄失敗：{exc} [hop:{hop}]"


def _handle_add_reflection(
    action: ActionAddReflection, author_role: str, hop: int
) -> str:
    """新增反思到 reflections 表。"""
    now = _now_iso()
    try:
        row_id = execute_write(
            "INSERT INTO reflections (author_role, content, created_at) VALUES (?, ?, ?)",
            (author_role, action.text, now),
        )
        return f"💭 反思 #{row_id} 已儲存 [hop:{hop}]"
    except Exception as exc:
        _logger.error("add_reflection DB 寫入失敗：%s", exc)
        return f"❌ 儲存反思失敗：{exc} [hop:{hop}]"


if __name__ == "__main__":
    """冒煙測試 handle_action（不需要 claude -p）。"""
    from agent.intent_engine import ActionAddNote, ActionNone

    print("TC1 happy path：handle_action(ActionAddNote, ...)")
    result = handle_action(
        ActionAddNote(action="add_note", text="測試筆記"),
        author_role="B",
        channel_id="123",
        hop=0,
    )
    print(f"  result: {result!r}")
    assert result is not None and "筆記" in result, "應回傳筆記儲存確認"
    print("  PASS")

    print("TC2 edge case：handle_action(ActionNone, ...) 回傳 None")
    result2 = handle_action(
        ActionNone(action="none"),
        author_role="B",
        channel_id="123",
    )
    assert result2 is None, "ActionNone 應回傳 None"
    print("  PASS")
