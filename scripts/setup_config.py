#!/usr/bin/env python3
"""
配置设置脚本 (调用已有 Config)
"""

import sys
import json
from pathlib import Path
from dataclasses import asdict
# 把项目根目录加到Python路径里
sys.path.append(str(Path(__file__).parent.parent.resolve()))
from config import GlobalConfig



def create_config_file():
    print("🔧 Agent 配置设置")
    print("=" * 50)

    config = GlobalConfig()  # 先用默认值实例化

    print("\n📡 OpenAI 配置:")
    openai_api_key = input(f"请输入 OpenAI API 密钥 (当前: {'已设置' if config.openai.api_key else '未设置'}, 留空跳过): ").strip()
    if openai_api_key:
        config.openai.api_key = openai_api_key
    openai_model = input(f"OpenAI 模型 (当前: {config.openai.model}, 留空跳过): ").strip()
    if openai_model:
        config.openai.model = openai_model

    print("\n🖥️  vLLM Chat 配置:")
    vllm_base_url = input(
        f"vLLM Chat 服务器地址 (当前: {config.vllm_chat.base_url}, 留空跳过): "
    ).strip()
    if vllm_base_url:
        config.vllm_chat.base_url = vllm_base_url
    vllm_model = input(
        f"vLLM Chat 模型名称 (当前: {config.vllm_chat.model_name}, 留空跳过): "
    ).strip()
    if vllm_model:
        config.vllm_chat.model_name = vllm_model

    print("\n🧠 vLLM Embedding 配置:")
    vllm_embed_base_url = input(
        f"vLLM Embedding 服务器地址 (当前: {config.vllm_embed.base_url}, 留空跳过): "
    ).strip()
    if vllm_embed_base_url:
        config.vllm_embed.base_url = vllm_embed_base_url
    vllm_embed_model = input(
        f"vLLM Embedding 模型名称 (当前: {config.vllm_embed.model_name}, 留空跳过): "
    ).strip()
    if vllm_embed_model:
        config.vllm_embed.model_name = vllm_embed_model

    print("\n🎯 检测配置:")
    default_strategy = input(f"默认检测策略 (当前: {config.detection.default_strategy}, 留空跳过): ").strip()
    if default_strategy:
        config.detection.default_strategy = default_strategy

    print("\n🤖 Agent 配置:")
    agent_name = input(f"Agent 名称 (当前: {config.agent.name}, 留空跳过): ").strip()
    if agent_name:
        config.agent.name = agent_name
    verbose = input(f"详细输出模式 (y/n, 当前: {'y' if config.agent.verbose else 'n'}, 留空跳过): ").strip().lower()
    if verbose in ['y', 'yes']:
        config.agent.verbose = True
    elif verbose in ['n', 'no']:
        config.agent.verbose = False

    print("\n📚 RAG 配置:")
    rag_chunk_max_chars = input(
        f"RAG chunk_max_chars (当前: {config.rag.chunk_max_chars}, 留空跳过): "
    ).strip()
    if rag_chunk_max_chars:
        config.rag.chunk_max_chars = int(rag_chunk_max_chars)
    rag_chunk_overlap = input(
        f"RAG chunk_overlap (当前: {config.rag.chunk_overlap}, 留空跳过): "
    ).strip()
    if rag_chunk_overlap:
        config.rag.chunk_overlap = int(rag_chunk_overlap)
    rag_dense_k = input(
        f"RAG dense_k (当前: {config.rag.dense_k}, 留空跳过): "
    ).strip()
    if rag_dense_k:
        config.rag.dense_k = int(rag_dense_k)
    rag_sparse_k = input(
        f"RAG sparse_k (当前: {config.rag.sparse_k}, 留空跳过): "
    ).strip()
    if rag_sparse_k:
        config.rag.sparse_k = int(rag_sparse_k)
    rag_rrf_k = input(
        f"RAG rrf_k (当前: {config.rag.rrf_k}, 留空跳过): "
    ).strip()
    if rag_rrf_k:
        config.rag.rrf_k = int(rag_rrf_k)
    rag_rerank_k = input(
        f"RAG rerank_k (当前: {config.rag.rerank_k}, 留空跳过): "
    ).strip()
    if rag_rerank_k:
        config.rag.rerank_k = int(rag_rerank_k)
    rag_rerank_model = input(
        f"RAG rerank_model (当前: {config.rag.rerank_model}, 留空跳过): "
    ).strip()
    if rag_rerank_model:
        config.rag.rerank_model = rag_rerank_model

    # 保存配置文件
    config_file = Path(__file__).parent.parent / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)
    print(f"\n✅ 配置文件已创建: {config_file}")

    # 简单打印配置摘要
    print("\n📋 配置摘要:")
    print(f"   OpenAI API密钥: {'已设置' if config.openai.api_key else '未设置'}")
    print(f"   OpenAI 模型: {config.openai.model}")
    print(f"   vLLM Chat 地址: {config.vllm_chat.base_url}")
    print(f"   vLLM Chat 模型: {config.vllm_chat.model_name}")
    print(f"   vLLM Embedding 地址: {config.vllm_embed.base_url}")
    print(f"   vLLM Embedding 模型: {config.vllm_embed.model_name}")
    print(f"   默认策略: {config.detection.default_strategy}")
    print(f"   Agent 名称: {config.agent.name}")
    print(f"   详细模式: {config.agent.verbose}")

    return config_file


def create_env_file():
    print("\n🔧 创建环境变量文件")

    env_content = """# Agent 环境变量配置
# 复制此文件为 .env 并填入真实的API密钥

# OpenAI 配置
OPENAI_API_KEY=
OPENAI_MODEL=gpt-3.5-turbo

# vLLM Chat 配置
VLLM_BASE_URL=http://127.0.0.1:8000/v1
VLLM_MODEL_NAME=Qwen2.5-VL-7B-Instruct
VLLM_API_KEY=

# vLLM Embedding 配置
VLLM_EMBED_BASE_URL=http://127.0.0.1:8001/v1
VLLM_EMBED_MODEL_NAME=Qwen3-VL-Embedding-2B
VLLM_EMBED_API_KEY=

# 系统配置
HYBRID_AGENT_DEBUG=false
"""

    env_file = Path(__file__).parent.parent / ".env"
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)

    print(f"✅ 环境变量文件已创建: {env_file}")
    print("💡 请复制为 .env 文件并填入真实的API密钥")


def test_config():
    print("\n🧪 测试配置")

    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return

    errors = []
    warnings = []

    if not config.get("openai", {}).get("api_key"):
        warnings.append("OpenAI API 密钥未设置")

    if not config.get("agent", {}).get("name"):
        errors.append("Agent 名称未设置")

    print("📋 配置验证结果:")
    if errors:
        print("   ❌ 配置无效:")
        for err in errors:
            print(f"      - {err}")
    else:
        print("   ✅ 配置有效")

    if warnings:
        print("   ⚠️ 配置警告:")
        for warn in warnings:
            print(f"      - {warn}")

    print("\n📄 配置信息摘要:")
    print(f"   OpenAI API密钥: {'已设置' if config.get('openai', {}).get('api_key') else '未设置'}")
    print(f"   OpenAI 模型: {config.get('openai', {}).get('model', '未设置')}")
    print(f"   Agent 名称: {config.get('agent', {}).get('name', '未设置')}")
    print(f"   详细模式: {config.get('agent', {}).get('verbose', False)}")


def main():
    print("🚀 Agent 配置设置向导")
    print("=" * 50)

    while True:
        print("\n请选择操作:")
        print("1. 创建配置文件")
        print("2. 创建环境变量文件")
        print("3. 测试配置")
        print("4. 退出")

        choice = input("\n请输入选择 (1-4): ").strip()

        if choice == "1":
            create_config_file()
        elif choice == "2":
            create_env_file()
        elif choice == "3":
            test_config()
        elif choice == "4":
            print("👋 再见!")
            break
        else:
            print("❌ 无效选择，请重新输入")


if __name__ == "__main__":
    main()
