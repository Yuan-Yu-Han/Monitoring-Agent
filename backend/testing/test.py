"""
Interactive CLI for Monitoring Agent or Qwen3-VL-8B agent.

Features:
- Initialize the agent with tools
- Maintain conversation history
- Interactively chat with the agent in terminal
- Type 'exit' or 'quit' to leave
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain_core.messages import HumanMessage

# -----------------------------
# Step 1: Define Tools
# -----------------------------
@tool
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"

# -----------------------------
# Step 2: Initialize Model
# -----------------------------
model = ChatOpenAI(
    model="Qwen3-VL-8B-Instruct",
    api_key="EMPTY",                 # 如果是本地部署，可保留 EMPTY
    base_url="http://localhost:8000/v1"  # 本地服务地址
)

# -----------------------------
# Step 3: Create Agent
# -----------------------------
agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="You are a helpful assistant, use the tools to answer user questions.",
)

# -----------------------------
# Step 4: Interactive CLI Loop
# -----------------------------
def main():
    print("🤖 Monitoring Agent CLI (type 'exit' or 'quit' to leave)")
    history = []

    while True:
        user_input = input("\n👤 You: ")
        if user_input.strip().lower() in ["exit", "quit"]:
            print("👋 Goodbye!")
            break

        # 添加用户消息到对话历史
        history.append(HumanMessage(content=user_input))

        # 调用 agent
        result = agent.invoke({"messages": history})

        # 获取最后一条 AIMessage 并打印
        ai_msg = result["messages"][-1]
        print(f"\n🤖 Agent: {ai_msg.content}")

        # 更新对话历史，保留上下文
        history = result["messages"]

# -----------------------------
# Step 5: Entry Point
# -----------------------------
if __name__ == "__main__":
    main()
