from pathlib import Path
PROMPT_DIR = Path(__file__).parent

def load_prompt(name: str) -> str:
    """
    加载指定名称的 prompt 文件内容。

    Args:
        name (str): prompt 文件的名称（不含扩展名）。

    Returns:
        str: prompt 文件的内容。
    """
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file '{name}.txt' not found in {PROMPT_DIR}.")
    return path.read_text(encoding="utf-8")

if __name__ == "__main__":
    # 测试 load_prompt 函数
    try:
        prompt_name = "system_prompt"  # 替换为实际存在的 prompt 文件名（不含扩展名）
        prompt_content = load_prompt(prompt_name)
        print(f"✅ 成功加载 prompt '{prompt_name}':\n{prompt_content}")
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
