from scripts.test import agent   # 你现有的 agent
from langchain_core.messages import HumanMessage

def main():
    print("🤖 Monitoring Agent (type 'exit' to quit)")
    history = []

    while True:
        user_input = input("\n👤 You: ")
        if user_input.strip().lower() in ["exit", "quit"]:
            break

        history.append(HumanMessage(content=user_input))

        result = agent.invoke({"messages": history})

        # 取最后一条 AIMessage
        ai_msg = result["messages"][-1]
        print(f"\n🤖 Agent: {ai_msg.content}")

        history = result["messages"]  # 保留上下文

if __name__ == "__main__":
    main()