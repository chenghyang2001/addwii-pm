"""addwii-pm Discord Bot — M4 版本：包含 Bot-to-Bot 轉發與 hop 防迴圈機制。

設計原則：
- 只跳過自己的訊息（if message.author.id == self.user.id）
- 不用 if message.author.bot: return（否則 bot 看不到彼此）
- Bot-to-Bot：提取 [hop:N]，若 hop >= MAX_HOPS 或未被 @mention 則忽略
- IntentEngine 解析意圖 → handle_action 寫 DB → 附加到 claude 回應
"""
import asyncio
import datetime
import re

import discord

from agent.actions import handle_action
from agent.intent_engine import ActionNone, parse_intent
from agent.persona import build_system_prompt
from core.claude_cli import invoke_claude
from core.config import cfg
from core.db import execute_write, get_conn
from core.logger import setup_logger

# 從訊息尾部提取 [hop:N] 標記的正則
_HOP_RE = re.compile(r"\[hop:(\d+)\]")

# 最大 hop 次數（從 config 讀取，預設 3）
MAX_HOPS: int = getattr(cfg, "max_hops", 3)


def extract_hop(content: str) -> int:
    """從訊息內容末尾提取 hop 計數，未找到回傳 0。

    Args:
        content: Discord 訊息的文字內容

    Returns:
        hop 計數整數（0 表示原始人類訊息或無標記）
    """
    match = _HOP_RE.search(content)
    if match:
        return int(match.group(1))
    return 0


class AddwiiBot(discord.Client):
    """addwii-pm 專屬 Discord Bot（M4 版本）。

    每個 bot 實例代表一個 role（A/B/C），
    可處理真人訊息與 bot-to-bot @mention 訊息。
    """

    def __init__(self, role: str) -> None:
        """初始化 Bot。

        Args:
            role: 'A'/'B'/'C'，決定 bot 代表哪個角色
        """
        intents = discord.Intents.default()
        intents.message_content = True  # 必須開啟才能讀取訊息內容
        super().__init__(intents=intents)
        self.role = role.upper()
        self.logger = setup_logger(f"bot-{self.role}")

    async def on_ready(self) -> None:
        """Bot 上線時更新 agents 表的 discord_bot_id。"""
        self.logger.info("Bot %s 已上線，user ID = %s", self.role, self.user.id)
        try:
            execute_write(
                "UPDATE agents SET discord_bot_id = ? WHERE role = ?",
                (self.user.id, self.role),
            )
            self.logger.info("已更新 agents.discord_bot_id = %s", self.user.id)
        except Exception as exc:
            self.logger.error("更新 discord_bot_id 失敗：%s", exc)

    async def on_message(self, message: discord.Message) -> None:
        """處理收到的 Discord 訊息。

        過濾規則（M4 版本）：
        1. 自己的訊息 → 永遠 skip（防迴圈最基本規則）
        2. 不是 #team 頻道 → skip
        3. Bot 訊息 → 提取 hop，判斷是否應回應
        4. 真人訊息 → 只有對應主人的 bot 回應
        """
        # 過濾 1：自己的訊息（最重要，永遠不回應自己）
        if message.author.id == self.user.id:
            return

        # 過濾 2：不是 #team 頻道
        if message.channel.id != cfg.channel_id:
            return

        if message.author.bot:
            # Bot-to-Bot 處理
            await self._handle_bot_message(message)
            return

        # 真人訊息
        role = cfg.resolve_role(message.author.id)
        if role != self.role:
            return

        await self.process_human_message(message)

    async def _handle_bot_message(self, message: discord.Message) -> None:
        """處理其他 bot 發送的訊息（M4 bot-to-bot 轉發邏輯）。

        規則：
        - 提取 [hop:N]，若 hop >= MAX_HOPS → 停止（防無限迴圈）
        - 若自己（self.user）未在 @mentions → 忽略
        - 符合條件 → 呼叫 AI 回應，hop+1 後轉發

        Args:
            message: 來自其他 bot 的 Discord 訊息
        """
        hop = extract_hop(message.content)

        # 超過最大 hop → 停止
        if hop >= MAX_HOPS:
            self.logger.debug(
                "Bot 訊息 hop=%d >= MAX_HOPS=%d，忽略", hop, MAX_HOPS
            )
            return

        # 未被 @mention → 忽略
        if self.user not in message.mentions:
            return

        # 被 @mention + hop 未超限 → 處理
        self.logger.info(
            "收到 bot @mention（hop=%d）：%s...", hop, message.content[:30]
        )

        # 去除 @mention 前綴，取得純文字內容
        clean_content = re.sub(r"<@!?\d+>", "", message.content).strip()
        # 移除 [hop:N] 標記（避免重複累積）
        clean_content = _HOP_RE.sub("", clean_content).strip()

        db_context = _fetch_open_tasks_context()
        system_prompt = build_system_prompt(self.role, db_context=db_context)

        try:
            response = await invoke_claude(
                self.role,
                clean_content,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            self.logger.error("Bot-to-Bot Claude CLI 失敗：%s", exc)
            return

        # 附加新的 hop 標記（+1）
        next_hop = hop + 1
        try:
            await message.channel.send(f"{response} [hop:{next_hop}]")
        except Exception as exc:
            self.logger.error("Bot-to-Bot 發送失敗：%s", exc)

    async def process_human_message(self, message: discord.Message) -> None:
        """處理主人訊息：記錄→意圖解析→AI 回應→DB 寫入→發送→記錄回應。

        M4 新增：IntentEngine 解析意圖，若非 none 則呼叫 handle_action 寫 DB。

        Args:
            message: 來自主人的 Discord 訊息物件
        """
        content = message.content
        self.logger.info("收到主人訊息：%s... (%d 字)", content[:30], len(content))

        # 1. 記錄人類訊息到 messages 表
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
        try:
            execute_write(
                """INSERT INTO messages
                   (channel_id, sender_role, sender_type, content, hop_count, created_at)
                   VALUES (?, ?, 'human', ?, 0, ?)""",
                (str(message.channel.id), self.role, content, now),
            )
        except Exception as exc:
            self.logger.error("記錄人類訊息失敗：%s", exc)

        # 2. 組合 system prompt
        db_context = _fetch_open_tasks_context()
        system_prompt = build_system_prompt(self.role, db_context=db_context)

        # 3. 呼叫 Claude CLI 產生 AI 回應
        try:
            response = await invoke_claude(
                self.role,
                content,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            self.logger.error("Claude CLI 呼叫失敗：%s", exc)
            response = f"[系統錯誤] 無法取得 AI 回應：{exc}"

        # 4. 意圖解析（M4 新增）
        action_msg = None
        try:
            parsed = await parse_intent(self.role, content)
            if not isinstance(parsed, ActionNone):
                action_msg = handle_action(
                    parsed,
                    author_role=self.role,
                    channel_id=str(message.channel.id),
                    hop=0,
                )
        except Exception as exc:
            self.logger.error("IntentEngine 失敗：%s", exc)

        # 5. 組合最終回應（AI 回應 + 動作確認）
        final_response = response
        if action_msg:
            final_response = f"{response}\n\n{action_msg}"

        # 6. 回覆到頻道
        try:
            await message.channel.send(final_response)
            self.logger.info("已回覆：%s...", final_response[:50])
        except Exception as exc:
            self.logger.error("發送訊息失敗：%s", exc)
            return

        # 7. 記錄 agent 回應到 messages 表
        now_reply = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
        try:
            execute_write(
                """INSERT INTO messages
                   (channel_id, sender_role, sender_type, content, hop_count, created_at)
                   VALUES (?, ?, 'agent', ?, 0, ?)""",
                (str(message.channel.id), self.role, final_response, now_reply),
            )
        except Exception as exc:
            self.logger.error("記錄 agent 回應失敗：%s", exc)


def _fetch_open_tasks_context() -> str:
    """從 DB 查詢開放中的任務，組成 db_context 字串。

    Returns:
        格式化後的開放任務字串；若無任務則回傳空字串
    """
    try:
        with get_conn(read_only=True) as conn:
            rows = conn.execute(
                """SELECT id, title, assignee_role, deadline
                   FROM tasks
                   WHERE status IN ('open', 'in_progress')
                   ORDER BY deadline ASC
                   LIMIT 10"""
            ).fetchall()

        if not rows:
            return ""

        lines = ["開放任務清單："]
        for row in rows:
            deadline_str = row["deadline"] or "無期限"
            lines.append(
                f"- #{row['id']} [{row['assignee_role']}] {row['title']}（期限：{deadline_str}）"
            )
        return "\n".join(lines)

    except Exception:
        # 查詢失敗不中斷 bot 流程
        return ""


if __name__ == "__main__":
    import sys
    import unittest
    from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

    class TestAddwiiBot(unittest.IsolatedAsyncioTestCase):
        def setUp(self):
            with patch("discord.Client.__init__", return_value=None):
                self.bot = AddwiiBot.__new__(AddwiiBot)
                self.bot.role = "B"
                self.bot.logger = setup_logger("test-bot-B")
                mock_user = MagicMock()
                mock_user.id = 99999
                type(self.bot).user = PropertyMock(return_value=mock_user)

        def _make_message(self, author_id=888, is_bot=False, channel_id=None, content="測試訊息"):
            msg = MagicMock(spec=discord.Message)
            msg.author = MagicMock()
            msg.author.id = author_id
            msg.author.bot = is_bot
            msg.channel = MagicMock()
            msg.channel.id = channel_id or cfg.channel_id
            msg.content = content
            msg.mentions = []
            return msg

        async def test_tc1_self_message_skipped(self):
            """TC1：自己的訊息應被忽略。"""
            self.bot.process_human_message = AsyncMock()
            self.bot._handle_bot_message = AsyncMock()
            msg = self._make_message(author_id=self.bot.user.id)
            await self.bot.on_message(msg)
            self.bot.process_human_message.assert_not_called()
            self.bot._handle_bot_message.assert_not_called()

        async def test_tc2_bot_message_hop_exceeded(self):
            """TC2：bot 訊息 hop >= MAX_HOPS 應被忽略。"""
            msg = self._make_message(
                author_id=11111, is_bot=True,
                content=f"測試訊息 [hop:{MAX_HOPS}]"
            )
            msg.channel.send = AsyncMock()
            await self.bot._handle_bot_message(msg)
            msg.channel.send.assert_not_called()

        async def test_tc3_extract_hop(self):
            """TC3：extract_hop 正確解析 [hop:N]。"""
            assert extract_hop("訊息內容 [hop:2]") == 2
            assert extract_hop("沒有標記的訊息") == 0
            assert extract_hop("[hop:0] 開頭") == 0

        async def test_tc4_principal_message_processed(self):
            """TC4：主人訊息應觸發 process_human_message。"""
            self.bot.process_human_message = AsyncMock()
            principal_id = cfg.members["B"]["discord_user_id"]
            msg = self._make_message(author_id=principal_id)
            await self.bot.on_message(msg)
            self.bot.process_human_message.assert_called_once_with(msg)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestAddwiiBot)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
