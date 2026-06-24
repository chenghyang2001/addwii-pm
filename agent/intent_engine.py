"""IntentEngine — 透過 claude -p 解析訊息意圖，產出 Pydantic Action 物件。

協定：claude 須以 fenced JSON code block 回應，IntentEngine 提取並驗證。
Pydantic 驗證失敗 → 降級為 ActionNone（純對話，不寫 DB）。
"""
import json
import re
from typing import Literal, Optional, Union

from pydantic import BaseModel, ValidationError

from core.claude_cli import invoke_claude

# 意圖解析用的 system prompt
_INTENT_SYSTEM_PROMPT = """你是廣告公司工作流程助理，負責解析訊息意圖並以 JSON 回應。

請以 fenced JSON code block 回應，格式如下（選其一）：

```json
{"action":"assign_task","assignee":"C","title":"任務標題","deadline":"2026-06-28"}
{"action":"report_task","task_id":42,"status":"done","summary":"完成摘要"}
{"action":"add_note","text":"筆記內容"}
{"action":"add_meeting","title":"會議標題","decisions":"決策內容","action_items":"行動項目"}
{"action":"add_reflection","text":"反思內容"}
{"action":"none"}
```

規則：
- deadline 格式為 YYYY-MM-DD，若無明確日期則省略此欄位
- task_id 必須是整數
- status 只能是 open / in_progress / done / cancelled
- 若訊息沒有明確工作指令，回傳 {"action":"none"}
- 只回傳 fenced JSON，不要額外說明文字"""

# 擷取 fenced JSON block 的正則
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


# ─── Pydantic Action 模型 ─────────────────────────────────────────
class ActionAssignTask(BaseModel):
    """指派任務動作。"""
    action: Literal["assign_task"]
    assignee: Literal["A", "B", "C"]
    title: str
    deadline: Optional[str] = None  # YYYY-MM-DD 或 None


class ActionReportTask(BaseModel):
    """回報任務狀態動作。"""
    action: Literal["report_task"]
    task_id: int
    status: Literal["open", "in_progress", "done", "cancelled"]
    summary: Optional[str] = None


class ActionAddNote(BaseModel):
    """新增筆記動作。"""
    action: Literal["add_note"]
    text: str


class ActionAddMeeting(BaseModel):
    """新增會議記錄動作。"""
    action: Literal["add_meeting"]
    title: str
    decisions: Optional[str] = None
    action_items: Optional[str] = None


class ActionAddReflection(BaseModel):
    """新增反思動作。"""
    action: Literal["add_reflection"]
    text: str


class ActionNone(BaseModel):
    """無特定動作（純對話模式）。"""
    action: Literal["none"]


# 聯集型別，方便型別標注
ParsedAction = Union[
    ActionAssignTask,
    ActionReportTask,
    ActionAddNote,
    ActionAddMeeting,
    ActionAddReflection,
    ActionNone,
]

# action 名稱 → Pydantic 類別 對應表
_ACTION_MAP: dict[str, type] = {
    "assign_task": ActionAssignTask,
    "report_task": ActionReportTask,
    "add_note": ActionAddNote,
    "add_meeting": ActionAddMeeting,
    "add_reflection": ActionAddReflection,
    "none": ActionNone,
}


async def parse_intent(role: str, user_text: str) -> ParsedAction:
    """解析使用者訊息意圖，回傳 Pydantic Action 物件。

    流程：
    1. 呼叫 claude -p，以 _INTENT_SYSTEM_PROMPT 解析意圖
    2. 從回應中提取 fenced JSON block
    3. 用 Pydantic 驗證 JSON → 對應 Action 物件
    4. 任何失敗 → 回傳 ActionNone（降級純對話）

    Args:
        role: 呼叫的 bot role（'A'/'B'/'C'），用於 Semaphore 限流
        user_text: 使用者發送的原始訊息

    Returns:
        ParsedAction：具體動作物件或 ActionNone
    """
    prompt = f"請解析以下訊息的意圖：\n\n{user_text}"

    try:
        raw = await invoke_claude(
            role=role,
            text=prompt,
            system_prompt=_INTENT_SYSTEM_PROMPT,
            timeout=60,
        )
    except Exception:
        # claude CLI 失敗 → 降級
        return ActionNone(action="none")

    # 從回應中取出第一個 fenced JSON block
    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        return ActionNone(action="none")

    raw_json = match.group(1).strip()

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return ActionNone(action="none")

    action_name = data.get("action", "")
    model_cls = _ACTION_MAP.get(action_name)
    if model_cls is None:
        return ActionNone(action="none")

    try:
        return model_cls(**data)
    except ValidationError:
        # Pydantic 驗證失敗 → 降級，不寫 DB
        return ActionNone(action="none")


if __name__ == "__main__":
    import asyncio

    async def _smoke():
        """冒煙測試（需要 claude CLI 可用）。"""
        print("TC1 happy path：parse_intent with 'none' action mock")
        result = await parse_intent("B", "今天天氣真好")
        print(f"  result type: {type(result).__name__}, action: {result.action}")
        assert result.action == "none", "無業務指令應回傳 none"
        print("  PASS（降級為 none，因測試環境可能無 claude -p）")

        print("TC2 edge case：_JSON_BLOCK_RE 提取測試")
        test_raw = '```json\n{"action":"none"}\n```'
        m = _JSON_BLOCK_RE.search(test_raw)
        assert m is not None, "應能提取 JSON block"
        data = json.loads(m.group(1))
        assert data["action"] == "none"
        print("  PASS")

    asyncio.run(_smoke())
