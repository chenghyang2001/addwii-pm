"""addwii-pm Discord Bot — M2 版本：處理真人→Bot 對話迴路。

M4 版本才加入 Bot-to-Bot 轉發與 hop 防迴圈機制。
"""
import asyncio
import discord
import datetime

from core.config import cfg
from core.db import execute_write, get_conn
from core.logger import setup_logger
from core.claude_cli import invoke_claude
from agent.persona import build_system_prompt


class AddwiiBot(discord.Client):
    """addwii-pm 專屬 Discord Bot。

    每個 bot 實例代表一個 role（A/B/C），只回應自己主人的訊息。
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

        過濾規則（M2 版本）：
        1. 自己的訊息 → 永遠 skip
        2. 其他 bot 訊息 → M2 暫時 skip（M4 才處理）
        3. 不是 #team 頻道 → skip
        4. 不是自己主人（對應 role 的 discord_user_id）→ skip
        """
        # 過濾 1：自己的訊息
        if message.author.id == self.user.id:
            return

        # 過濾 2：其他 bot（M2 暫時不處理 bot-to-bot）
        if message.author.bot:
            return

        # 過濾 3：不是 #team 頻道
        if message.channel.id != cfg.channel_id:
            return

        # 過濾 4：不是自己主人
        role = cfg.resolve_role(message.author.id)
        if role != self.role:
            return

        await self.process_human_message(message)

    async def process_human_message(self, message: discord.Message) -> None:
        """處理主人訊息：記錄→AI 回應→發送→記錄回應。

        Args:
            message: 來自主人的 Discord 訊息物件
        """
        content = message.content
        self.logger.info("收到主人訊息：%s... (%d 字)", content[:30], len(content))

        # 1. 記錄人類訊息到 messages 表
        now = datetime.datetime.utcnow().isoformat()
        try:
            execute_write(
                """INSERT INTO messages
                   (channel_id, sender_role, sender_type, content, hop_count, created_at)
                   VALUES (?, ?, 'human', ?, 0, ?)""",
                (str(message.channel.id), self.role, content, now),
            )
        except Exception as exc:
            self.logger.error("記錄人類訊息失敗：%s", exc)

        # 2. 組合 system prompt（附加開放任務清單）
        db_context = _fetch_open_tasks_context()
        system_prompt = build_system_prompt(self.role, db_context=db_context)

        # 3. 呼叫 Claude CLI
        try:
            response = await invoke_claude(
                self.role,
                content,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            self.logger.error("Claude CLI 呼叫失敗：%s", exc)
            response = f"[系統錯誤] 無法取得 AI 回應：{exc}"

        # 4. 回覆到頻道
        try:
            await message.channel.send(response)
            self.logger.info("已回覆：%s...", response[:50])
        except Exception as exc:
            self.logger.error("發送訊息失敗：%s", exc)
            return

        # 5. 記錄 agent 回應到 messages 表
        now_reply = datetime.datetime.utcnow().isoformat()
        try:
            execute_write(
                """INSERT INTO messages
                   (channel_id, sender_role, sender_type, content, hop_count, created_at)
                   VALUES (?, ?, 'agent', ?, 0, ?)""",
                (str(message.channel.id), self.role, response, now_reply),
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

    except Exception as exc:
        # 查詢失敗不中斷 bot 流程，回傳空字串
        return ""


if __name__ == "__main__":
    # 單元測試（不需要真實 Discord 連線）
    import unittest
    from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

    class TestAddwiiBot(unittest.IsolatedAsyncioTestCase):
        def setUp(self):
            """建立 AddwiiBot 實例（不連線 Discord）。"""
            with patch("discord.Client.__init__", return_value=None):
                self.bot = AddwiiBot.__new__(AddwiiBot)
                self.bot.role = "B"
                self.bot.logger = setup_logger("test-bot-B")
                # 使用 PropertyMock 覆寫唯讀 property user
                # discord.Client.user 是 @property 無 setter，不可直接賦值
                mock_user = MagicMock()
                mock_user.id = 99999
                type(self.bot).user = PropertyMock(return_value=mock_user)

        def _make_message(self, author_id=888, is_bot=False, channel_id=None):
            """建立模擬 Discord Message。"""
            msg = MagicMock(spec=discord.Message)
            msg.author = MagicMock()
            msg.author.id = author_id
            msg.author.bot = is_bot
            msg.channel = MagicMock()
            msg.channel.id = channel_id or cfg.channel_id
            msg.content = "測試訊息"
            return msg

        async def test_tc1_self_message_skipped(self):
            """TC1：自己的訊息應被忽略（process_human_message 不被呼叫）。"""
            self.bot.process_human_message = AsyncMock()
            msg = self._make_message(author_id=self.bot.user.id)
            await self.bot.on_message(msg)
            self.bot.process_human_message.assert_not_called()

        async def test_tc2_non_principal_skipped(self):
            """TC2：不是主人的真人訊息應被忽略。"""
            self.bot.process_human_message = AsyncMock()
            # author_id = 777 在 config 中沒有對應 role
            msg = self._make_message(author_id=777)
            await self.bot.on_message(msg)
            self.bot.process_human_message.assert_not_called()

        async def test_tc3_principal_message_processed(self):
            """TC3：主人的訊息應觸發 process_human_message。"""
            self.bot.process_human_message = AsyncMock()
            # 使用 config.json 中 B 的真實 discord_user_id
            principal_id = cfg.members["B"]["discord_user_id"]
            msg = self._make_message(author_id=principal_id)
            await self.bot.on_message(msg)
            self.bot.process_human_message.assert_called_once_with(msg)

    import sys
    # 跑測試
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAddwiiBot)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
