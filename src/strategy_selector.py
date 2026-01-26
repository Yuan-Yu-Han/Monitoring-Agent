#!/usr/bin/env python3
"""
检测策略选择器
处理用户交互和智能策略选择
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple
from detection_agent.strategies.strategies import DetectionMode, DetectionCapabilities, strategy_manager

# 配置日志
logger = logging.getLogger(__name__)


class DetectionStrategySelector:
    """检测策略选择器"""
    
    def __init__(self):
        self.strategy_manager = strategy_manager
        self.user_preferences = {}
    
    def extract_detection_mode_from_input(self, user_input: str) -> Tuple[Optional[str], Optional[DetectionMode]]:
        """
        从用户输入中提取检测方式和模式
        Returns:
            (strategy_name, detection_mode)
        """
        user_input_lower = user_input.lower().strip()
        
        # 提取检测方式
        strategy_name = None
        
        # 首先检查是否是编号选择
        try:
            # 获取可用策略
            available_strategies = self.strategy_manager.get_available_strategies()
            strategy_names = [s.name for s in available_strategies]
            
            # 检查是否是有效的编号
            if user_input_lower.isdigit():
                choice_num = int(user_input_lower)
                if 1 <= choice_num <= len(available_strategies):
                    strategy_name = strategy_names[choice_num - 1]
                    logger.info(f"Selected strategy by number {choice_num}: {strategy_name}")
        except Exception as e:
            logger.warning(f"Failed to parse number selection: {e}")
        
        # 如果不是编号选择，则进行关键词匹配
        if not strategy_name:
            strategy_keywords = {
                "qwen_vl": ["本地agent", "本地智能", "本地", "qwen", "vllm", "agent", "复杂分析"],
                "local_yolo": ["本地yolo", "yolo", "快速检测", "实时检测", "高速检测", "快速"],
                "online_api": ["在线", "openai", "gpt", "云端", "api", "gpt-4", "gpt-4v", "gpt-4o", "gpt4o", "最强精度", "最高精度", "最新模型", "智能检测"]
            }
            
            for strategy, keywords in strategy_keywords.items():
                if any(keyword in user_input_lower for keyword in keywords):
                    strategy_name = strategy
                    break
        
        # 提取检测模式
        detection_mode = DetectionMode.DEFAULT
        
        mode_keywords = {
            DetectionMode.FIRE_FOCUS: ["火灾", "火", "fire", "火焰"],
            DetectionMode.SAFETY_FOCUS: ["安全", "人员", "safety", "安全帽"],
            DetectionMode.VEHICLE_FOCUS: ["车辆", "车", "vehicle", "消防车"],
            DetectionMode.EMERGENCY: ["紧急", "emergency", "危险"]
        }
        
        for mode, keywords in mode_keywords.items():
            if any(keyword in user_input_lower for keyword in keywords):
                detection_mode = mode
                break
        
        return strategy_name, detection_mode
    
    def get_strategy_selection_prompt(self, available_strategies: List[DetectionCapabilities]) -> str:
        """生成策略选择提示"""
        prompt_parts = [
            "🎯 请选择检测方式:",
            ""
        ]
        
        for i, strategy in enumerate(available_strategies, 1):
            prompt_parts.append(f"{i}. {strategy.display_name}")
        
        prompt_parts.extend([
            "",
            "💡 输入编号 (1-3) 或直接说检测方式名称"
        ])
        
        return "\n".join(prompt_parts)
    
    async def select_strategy_interactive(self, user_input: str, image_path: str = None) -> Tuple[str, DetectionMode]:
        """
        交互式选择检测策略
        Args:
            user_input: 用户输入
            image_path: 图片路径（用于智能推荐）
        Returns:
            (strategy_name, detection_mode)
        """
        # 首先尝试从输入中提取
        strategy_name, detection_mode = self.extract_detection_mode_from_input(user_input)
        
        if strategy_name:
            available_strategies = self.strategy_manager.get_available_strategies()
            available_names = [s.name for s in available_strategies]
            
            if strategy_name in available_names:
                return strategy_name, detection_mode
        
        # 如果没有明确指定，显示选择菜单
        available_strategies = self.strategy_manager.get_available_strategies()
        
        if not available_strategies:
            # 如果没有可用策略，返回默认策略 - 优先使用LocalYOLO
            return "local_yolo", detection_mode
        
        # 生成选择提示
        selection_prompt = self.get_strategy_selection_prompt(available_strategies)
        
        # 这里需要与用户交互，暂时返回推荐的策略
        recommended_strategy = self.recommend_strategy(image_path, available_strategies)
        
        return recommended_strategy, detection_mode
    
    def recommend_strategy(self, image_path: str = None, available_strategies: List[DetectionCapabilities] = None) -> str:
        """
        智能推荐检测策略
        Args:
            image_path: 图片路径
            available_strategies: 可用策略列表
        Returns:
            推荐的策略名称
        """
        if not available_strategies:
            available_strategies = self.strategy_manager.get_available_strategies()
        
        if not available_strategies:
            return "local_yolo"  # 默认策略 - 优先使用LocalYOLO
        
        # 基于用户偏好和历史使用情况推荐
        # 这里可以实现更复杂的推荐逻辑
        
        # 简单推荐逻辑：
        # 1. 如果有实时性需求，推荐YOLO
        # 2. 如果需要高精度，推荐OpenAI API
        # 3. 默认推荐本地Agent（平衡性能和精度）
        
        strategy_names = [s.name for s in available_strategies]
        
        # 优先级顺序 - 优先使用LocalYOLO策略
        preference_order = ["local_yolo", "qwen_vl", "online_api"]
        
        for preferred in preference_order:
            if preferred in strategy_names:
                return preferred
        
        # 如果都没有，返回第一个可用的
        return strategy_names[0] if strategy_names else "local_yolo"
    
    def format_strategy_info(self, strategy_name: str) -> str:
        """格式化策略信息"""
        strategy = self.strategy_manager.get_strategy(strategy_name)
        if not strategy:
            return f"❌ 策略 '{strategy_name}' 不存在"
        
        capabilities = strategy.capabilities
        status = "✅ 可用" if capabilities.available else "❌ 不可用"
        
        info_parts = [
            f"🎯 **{capabilities.display_name}** {status}",
            f"📝 {capabilities.description}",
            f"⏱️  预计时间: {capabilities.estimated_time}",
            f"💰 成本: {capabilities.cost}",
            f"🎯 精度: {capabilities.accuracy} | ⚡ 速度: {capabilities.speed}",
            f"🔢 最大并发: {capabilities.max_concurrent}"
        ]
        
        if capabilities.fallback_strategy:
            info_parts.append(f"🔄 降级策略: {capabilities.fallback_strategy}")
        
        return "\n".join(info_parts)
    
    async def get_strategy_status_report(self) -> str:
        """获取策略状态报告"""
        health_status = await self.strategy_manager.health_check_all()
        available_strategies = self.strategy_manager.get_available_strategies()
        
        report_parts = [
            "📊 **检测策略状态报告**",
            ""
        ]
        
        for strategy_name, is_healthy in health_status.items():
            strategy = self.strategy_manager.get_strategy(strategy_name)
            if strategy:
                status_icon = "✅" if is_healthy else "❌"
                status_text = "健康" if is_healthy else "异常"
                
                report_parts.extend([
                    f"{status_icon} **{strategy.capabilities.display_name}**: {status_text}",
                    f"   可用性: {'是' if strategy.capabilities.available else '否'}",
                    f"   最大并发: {strategy.capabilities.max_concurrent}",
                    ""
                ])
        
        report_parts.extend([
            f"📈 总可用策略数: {len(available_strategies)}",
            f"📈 健康策略数: {sum(health_status.values())}"
        ])
        
        return "\n".join(report_parts)


# 全局策略选择器实例
strategy_selector = DetectionStrategySelector()
