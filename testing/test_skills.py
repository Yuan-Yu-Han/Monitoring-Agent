#!/usr/bin/env python3
"""
Skills 测试脚本
演示如何使用封装好的 Skills 进行监控分析
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.skills import (
    analyze_monitoring_event,
    quick_detect,
    batch_analyze,
    compare_events
)


def test_analyze_monitoring_event():
    """测试一键分析功能"""
    print("\n" + "="*60)
    print("测试 1: analyze_monitoring_event - 一键分析")
    print("="*60)

    # 场景1：使用 event_id（推荐）
    print("\n【场景1】使用 event_id 分析事件:")
    result = analyze_monitoring_event.invoke({
        "event_id": "20240315_143022_alarm_a3b2c1",
        "severity": "warning",
        "save_report": True,
        "region": "entrance"
    })
    print(result)

    # 场景2：使用 query 模糊查找
    print("\n【场景2】使用 query 模糊查找:")
    result = analyze_monitoring_event.invoke({
        "query": "test.jpg",
        "severity": "info"
    })
    print(result)


def test_quick_detect():
    """测试快速检测功能"""
    print("\n" + "="*60)
    print("测试 2: quick_detect - 快速检测")
    print("="*60)

    # 场景1：快速检测并绘制框图
    print("\n【场景1】快速检测（带标注框）:")
    result = quick_detect.invoke({
        "query": "test.jpg",
        "draw_boxes": True
    })
    print(result)

    # 场景2：只检测不绘制
    print("\n【场景2】只检测不绘制:")
    result = quick_detect.invoke({
        "query": "test.jpg",
        "draw_boxes": False
    })
    print(result)


def test_batch_analyze():
    """测试批量分析功能"""
    print("\n" + "="*60)
    print("测试 3: batch_analyze - 批量分析")
    print("="*60)

    # 场景：分析 inputs 目录下的所有 jpg 图片
    print("\n【场景】批量分析 inputs 目录:")
    result = batch_analyze.invoke({
        "directory": "inputs",
        "pattern": "*.jpg",
        "severity": "info",
        "max_images": 3
    })
    print(result)


def test_compare_events():
    """测试对比分析功能"""
    print("\n" + "="*60)
    print("测试 4: compare_events - 对比分析")
    print("="*60)

    # 场景：对比两个事件
    print("\n【场景】对比两个事件:")
    result = compare_events.invoke({
        "query_1": "before.jpg",
        "query_2": "after.jpg"
    })
    print(result)


def demo_skills_usage():
    """演示 Skills 的使用场景"""
    print("\n" + "🎯"*30)
    print("Skills 使用场景演示")
    print("🎯"*30)

    print("\n💡 **场景1: 处理监控告警事件**")
    print("   用户: '分析 event_20240315_alarm_001'")
    print("   推荐: analyze_monitoring_event(event_id='event_20240315_alarm_001')")
    print("   优势: 一步完成 find → detect → draw → report")

    print("\n💡 **场景2: 快速查看图片内容**")
    print("   用户: '看看这张图有什么'")
    print("   推荐: quick_detect(query='latest.jpg')")
    print("   优势: 快速检测，跳过报告生成")

    print("\n💡 **场景3: 分析今天的所有告警**")
    print("   用户: '分析今天的所有告警图片'")
    print("   推荐: batch_analyze(directory='outputs/alarm', pattern='2024031*')")
    print("   优势: 批量处理，自动汇总统计")

    print("\n💡 **场景4: 对比前后变化**")
    print("   用户: '对比早上和现在的监控画面'")
    print("   推荐: compare_events(event_id_1='morning', event_id_2='now')")
    print("   优势: 自动对比差异，找出变化")


def main():
    """主函数"""
    print("\n🚀 Skills 测试开始...")

    # 演示使用场景
    demo_skills_usage()

    # 选择要测试的功能
    print("\n" + "="*60)
    print("选择测试项目:")
    print("1. analyze_monitoring_event - 一键分析")
    print("2. quick_detect - 快速检测")
    print("3. batch_analyze - 批量分析")
    print("4. compare_events - 对比分析")
    print("5. 全部测试")
    print("0. 退出")
    print("="*60)

    try:
        choice = input("\n请输入选项 (0-5): ").strip()

        if choice == "1":
            test_analyze_monitoring_event()
        elif choice == "2":
            test_quick_detect()
        elif choice == "3":
            test_batch_analyze()
        elif choice == "4":
            test_compare_events()
        elif choice == "5":
            test_analyze_monitoring_event()
            test_quick_detect()
            test_batch_analyze()
            test_compare_events()
        elif choice == "0":
            print("\n👋 退出测试")
            return
        else:
            print("\n❌ 无效选项")

    except KeyboardInterrupt:
        print("\n\n👋 测试中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n✅ 测试完成!")


if __name__ == "__main__":
    main()
