#!/usr/bin/env python3
"""
监控Agent交互界面
提供命令行和Web界面两种交互方式
"""

import os
import sys
import argparse
from pathlib import Path
from hybrid_agent import create_monitoring_agent
from hybrid_agent_config import get_hybrid_config, load_config_from_file

async def command_line_interface():
    """命令行交互界面"""
    print("🤖 监控Agent交互界面")
    print("=" * 50)
    
    # 加载配置
    try:
        config = load_config_from_file("hybrid_agent_config.json")
        api_key = config.openai.api_key
    except Exception as e:
        print(f"⚠️ 无法加载配置文件: {e}")
        # 回退到环境变量
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ 请设置OpenAI API密钥:")
        print("   方法1: 运行 python setup_config.py 创建配置文件")
        print("   方法2: export OPENAI_API_KEY='your_api_key_here'")
        print("   方法3: python agent_chat.py --api-key your_key")
        return
    
    try:
        # 创建Agent
        print("🚀 正在初始化监控Agent...")
        agent = create_monitoring_agent(api_key)
        print("✅ Agent初始化完成!\n")
        
        # 显示使用说明
        print("💡 使用说明:")
        print("   - 直接输入文字与Agent对话")
        print("   - 输入 'image:/path/to/image.jpg' 检测图片")
        print("   - 输入 'history' 查看对话历史")
        print("   - 输入 'report' 生成监控报告")
        print("   - 输入 'clear' 清空记忆")
        print("   - 输入 'quit' 退出程序")
        print("=" * 50)
        
        # 主对话循环
        while True:
            try:
                # 获取用户输入
                user_input = input("\n👤 用户: ").strip()
                
                if not user_input:
                    continue
                
                # 处理特殊命令
                if user_input.lower() == 'quit':
                    print("👋 再见!")
                    break
                
                elif user_input.lower() == 'clear':
                    agent.clear_memory()
                    continue
                
                elif user_input.lower() == 'history':
                    history = agent.get_conversation_history()
                    print(f"\n📚 对话历史 (共{len(history)}条):")
                    for i, interaction in enumerate(history[-5:], 1):
                        print(f"  {i}. 用户: {interaction['user_input'][:50]}...")
                        print(f"     Agent: {interaction['agent_response'][:50]}...")
                    continue
                
                elif user_input.lower() == 'report':
                    # 生成报告
                    response = await agent.chat("请生成一份基于最近检测数据的监控报告")
                    print(f"\n🤖 Agent: {response}")
                    continue
                
                elif user_input.startswith('image:'):
                    # 图片检测
                    image_path = user_input[6:].strip()
                    if not os.path.exists(image_path):
                        print(f"❌ 图片文件不存在: {image_path}")
                        continue
                    
                    print("🔍 正在检测图片...")
                    response = await agent.chat(f"请检测这张图片中的安全隐患", image_path=image_path)
                    print(f"\n🤖 Agent: {response}")
                
                else:
                    # 普通对话
                    print("🧠 Agent正在思考...")
                    response = await agent.chat(user_input)
                    print(f"\n🤖 Agent: {response}")
                    
            except (EOFError, KeyboardInterrupt):
                print("\n👋 程序退出!")
                break
            except Exception as e:
                print(f"\n❌ 发生错误: {e}")
                
    except Exception as e:
        print(f"❌ Agent初始化失败: {e}")
        print("💡 请检查:")
        print("   1. OpenAI API密钥是否正确")
        print("   2. 网络连接是否正常")
        print("   3. 本地检测工具是否可用")

async def batch_detection_mode(image_dir: str, api_key: str):
    """批量检测模式"""
    print(f"📁 批量检测模式: {image_dir}")
    
    # 查找图片文件
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        image_files.extend(Path(image_dir).glob(ext))
    
    if not image_files:
        print(f"❌ 在 {image_dir} 中未找到图片文件")
        return
    
    print(f"📊 找到 {len(image_files)} 张图片")
    
    try:
        # 创建Agent
        agent = create_monitoring_agent(api_key)
        
        # 批量处理
        results = []
        for i, img_path in enumerate(image_files, 1):
            print(f"\n🖼️ 处理图片 [{i}/{len(image_files)}]: {img_path.name}")
            
            response = await agent.chat(f"检测图片中的目标", image_path=str(img_path))
            results.append({
                "image": str(img_path),
                "response": response
            })
            
            print(f"✅ 完成")
        
        # 生成总结报告
        print(f"\n📋 生成总结报告...")
        report_response = await agent.chat("请基于刚才的所有检测结果生成一份综合监控报告")
        print(f"\n📊 综合报告:\n{report_response}")
        
    except Exception as e:
        print(f"❌ 批量检测失败: {e}")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="监控Agent交互界面")
    parser.add_argument("--api-key", help="OpenAI API密钥")
    parser.add_argument("--batch", help="批量检测模式，指定图片目录")
    parser.add_argument("--image", help="单张图片检测")
    
    args = parser.parse_args()
    
    # 获取API密钥
    if args.api_key:
        api_key = args.api_key
    else:
        # 尝试从配置文件加载
        try:
            config = load_config_from_file("hybrid_agent_config.json")
            api_key = config.openai.api_key
        except Exception:
            # 回退到环境变量
            api_key = os.getenv("OPENAI_API_KEY")
    
    if args.batch:
        # 批量检测模式
        await batch_detection_mode(args.batch, api_key)
    elif args.image:
        # 单张图片检测
        if not api_key:
            print("❌ 请提供OpenAI API密钥")
            return
            
        try:
            agent = create_monitoring_agent(api_key)
            response = await agent.chat("检测这张图片", image_path=args.image)
            print(f"🤖 检测结果:\n{response}")
        except Exception as e:
            print(f"❌ 检测失败: {e}")
    else:
        # 交互式对话模式
        await command_line_interface()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
