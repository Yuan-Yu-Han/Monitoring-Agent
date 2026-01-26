from detection_agent.graph import build_graph
from detection_agent.state import AgentState
from detection_agent.tools import detect_image, safe_parse_json, draw_bboxes
from detection_agent.strategies.strategies import DetectionMode, strategy_manager
from detection_agent.strategy_selector import strategy_selector


def run_agent(image: str, detection_mode: str = "default", strategy_name: str = None):
    """
    运行推理 (兼容旧版本)
    Args:
        image: 图片路径或URL
        detection_mode: 检测模式 (default/fire_focus/safety_focus/vehicle_focus/emergency)
        strategy_name: 指定检测策略 (可选)
    """
    # 转换检测模式
    try:
        mode = DetectionMode(detection_mode)
    except ValueError:
        mode = DetectionMode.DEFAULT
    
    # 如果指定了策略，使用新架构
    if strategy_name:
        # 在同步环境中运行异步函数
        import asyncio
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在异步环境中，创建新任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, run_agent_async(image, mode, strategy_name))
                    return future.result()
            else:
                # 如果没有运行的事件循环，直接运行
                return asyncio.run(run_agent_async(image, mode, strategy_name))
        except RuntimeError:
            # 如果没有事件循环，创建新的
            return asyncio.run(run_agent_async(image, mode, strategy_name))
    
    # 否则使用原有逻辑（向后兼容）
    graph = build_graph()
    state: AgentState = {
        "input_image": image,
        "detection_mode": detection_mode
    }
    updated_state = graph.invoke(state)
    return updated_state


async def run_agent_async(image: str, detection_mode: DetectionMode = DetectionMode.DEFAULT, 
                         strategy_name: str = None) -> dict:
    """
    异步运行推理
    Args:
        image: 图片路径或URL
        detection_mode: 检测模式
        strategy_name: 指定检测策略
    Returns:
        检测结果字典（兼容原有格式）
    """
    # 如果没有指定策略，使用配置中的默认策略
    if not strategy_name:
        try:
            from hybrid_agent_config import get_hybrid_config
            config = get_hybrid_config()
            strategy_name = config.detection.default_strategy
        except Exception as e:
            print(f"⚠️ 无法获取配置中的默认策略，使用local_yolo: {e}")
            strategy_name = "local_yolo"
    
    try:
        # 使用策略管理器进行检测
        result = await strategy_manager.detect_with_fallback(strategy_name, image, detection_mode)
        
        # 转换为原有格式
        return {
            "detections": result.detections,
            "output_image": result.output_image,
            "raw_result": result.metadata.get("raw_result", ""),
            "success": result.success,
            "error": result.error,
            "strategy_used": result.strategy_used,
            "processing_time": result.processing_time
        }
        
    except Exception as e:
        # 如果新架构失败，回退到原有逻辑
        print(f"⚠️ 新架构检测失败，回退到原有逻辑: {e}")
        graph = build_graph()
        state: AgentState = {
            "input_image": image,
            "detection_mode": detection_mode.value
        }
        updated_state = graph.invoke(state)
        return updated_state


async def run_agent_with_strategy_selection(image: str, user_input: str = "") -> dict:
    """
    使用策略选择器运行推理
    Args:
        image: 图片路径或URL
        user_input: 用户输入（用于策略选择）
    Returns:
        检测结果字典
    """
    try:
        # 使用策略选择器选择策略
        strategy_name, detection_mode = await strategy_selector.select_strategy_interactive(user_input, image)
        
        print(f"🎯 选择检测策略: {strategy_name}")
        print(f"🎯 检测模式: {detection_mode.value}")
        
        # 执行检测
        return await run_agent_async(image, detection_mode, strategy_name)
        
    except Exception as e:
        print(f"❌ 策略选择失败，使用默认策略: {e}")
        return await run_agent_async(image, DetectionMode.DEFAULT, "local_yolo")
