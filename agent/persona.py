"""Persona 模組 — 讀取 personas/*.md 並組合 Claude system prompt。"""
from pathlib import Path


# personas/ 目錄位置（相對於本檔案往上一層）
_PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"


def build_system_prompt(role: str, db_context: str = "") -> str:
    """組合指定 role 的 system prompt。

    讀取 personas/_base.md 和 personas/role_{a/b/c}.md，
    合併後若有 db_context 則附加於末尾。

    Args:
        role: 角色代碼，'A'/'B'/'C'（大小寫均可）
        db_context: 目前開放任務、最近筆記等動態資訊；
                    非空時附加到 system prompt 末尾

    Returns:
        組合後的完整 system prompt 字串

    Raises:
        FileNotFoundError: personas/_base.md 或對應 role_x.md 不存在
        ValueError: role 不是 'A'/'B'/'C' 其中之一
    """
    valid_roles = {"A", "B", "C"}
    role_upper = role.upper()
    if role_upper not in valid_roles:
        raise ValueError(f"不合法的 role：{role!r}，必須是 A/B/C 其中之一")

    # 讀取基礎規則
    base_path = _PERSONAS_DIR / "_base.md"
    if not base_path.exists():
        raise FileNotFoundError(f"找不到基礎 persona 檔案：{base_path}")

    # 讀取角色特定規則
    role_path = _PERSONAS_DIR / f"role_{role_upper.lower()}.md"
    if not role_path.exists():
        raise FileNotFoundError(f"找不到角色 persona 檔案：{role_path}")

    base_content = base_path.read_text(encoding="utf-8")
    role_content = role_path.read_text(encoding="utf-8")

    # 合併：基礎 + 角色
    combined = f"{base_content}\n\n{role_content}"

    # 附加動態 DB 狀態
    if db_context:
        combined += f"\n\n## 目前狀態\n{db_context}"

    return combined


if __name__ == "__main__":
    # 冒煙測試
    print("TC1 happy path：build_system_prompt('B')")
    try:
        prompt = build_system_prompt("B")
        assert len(prompt) > 0, "prompt 不應為空"
        print(f"  長度：{len(prompt)} 字元  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")

    print("TC2 edge case：build_system_prompt('B', db_context='無開放任務')")
    try:
        prompt = build_system_prompt("B", db_context="無開放任務")
        assert "目前狀態" in prompt, "應包含 '目前狀態' 段落"
        assert "無開放任務" in prompt, "應包含 db_context 內容"
        print(f"  長度：{len(prompt)} 字元  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
