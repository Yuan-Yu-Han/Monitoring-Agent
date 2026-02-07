"""
Tool 调用拦截器 - 显示 Tool 执行过程
监控每个 tool 的调用、参数和输出
"""

import sys
from typing import Any, Callable, Dict, List
import json
from datetime import datetime


class ToolCallInterceptor:
    """工具调用拦截器 - 记录和显示工具执行过程"""
    
    def __init__(self, enable_verbose: bool = True):
        self.enable_verbose = enable_verbose
        self.call_stack: List[Dict[str, Any]] = []
        self.call_count = 0
    
    def log_tool_call(self, tool_name: str, args: Dict[str, Any]) -> None:
        """记录工具调用开始"""
        self.call_count += 1
        call_id = self.call_count
        
        if not self.enable_verbose:
            return
        
        print("\n" + "="*70)
        print(f"🔧 [Tool #{call_id}] 工具调用")
        print("="*70)
        print(f"📛 工具名称: {tool_name}")
        print(f"⏰ 调用时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        print(f"📥 传入参数:")
        
        for key, value in args.items():
            print(f"   • {key}: ", end="")
            if isinstance(value, str) and len(value) > 100:
                print(f"{value[:100]}...")
            elif isinstance(value, (dict, list)):
                try:
                    value_str = json.dumps(value, ensure_ascii=False, indent=6)[:200]
                    print(value_str)
                except:
                    print(str(value)[:100])
            else:
                print(value)
        
        self.call_stack.append({
            "id": call_id,
            "name": tool_name,
            "args": args,
            "start_time": datetime.now()
        })
    
    def log_tool_step(self, message: str) -> None:
        """记录工具执行步骤"""
        if not self.enable_verbose:
            return
        print(f"   ✨ {message}")
    
    def log_tool_result(self, result: Any, success: bool = True) -> None:
        """记录工具执行结果"""
        if not self.enable_verbose:
            return
        
        if self.call_stack:
            call_info = self.call_stack[-1]
            duration = (datetime.now() - call_info["start_time"]).total_seconds()
            
            status_icon = "✅" if success else "❌"
            print(f"\n📤 执行结果 ({status_icon}):")
            
            if isinstance(result, str):
                # 字符串结果，显示前500个字符
                if len(result) > 500:
                    print(f"{result[:500]}\n... (已截断，共{len(result)}字符)")
                else:
                    print(result)
            elif isinstance(result, dict):
                try:
                    print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
                except:
                    print(str(result)[:500])
            else:
                print(str(result)[:500])
            
            print(f"\n⏱️  执行耗时: {duration:.3f}s")
            print("="*70)
            self.call_stack.pop()
    
    def log_error(self, error: str) -> None:
        """记录错误"""
        if not self.enable_verbose:
            return
        print(f"\n❌ 错误: {error}")
        print("="*70)
    
    def reset_counter(self) -> None:
        """重置调用计数器（每次新对话时调用）"""
        self.call_count = 0
        self.call_stack.clear()


# 全局拦截器实例
_tool_interceptor = ToolCallInterceptor(enable_verbose=True)


def get_tool_interceptor() -> ToolCallInterceptor:
    """获取全局拦截器实例"""
    return _tool_interceptor


def log_tool_call(tool_name: str, **kwargs) -> None:
    """便捷函数：记录工具调用"""
    _tool_interceptor.log_tool_call(tool_name, kwargs)


def log_tool_step(message: str) -> None:
    """便捷函数：记录工具步骤"""
    _tool_interceptor.log_tool_step(message)


def log_tool_result(result: Any, success: bool = True) -> None:
    """便捷函数：记录工具结果"""
    _tool_interceptor.log_tool_result(result, success)


def log_tool_error(error: str) -> None:
    """便捷函数：记录工具错误"""
    _tool_interceptor.log_error(error)


def reset_tool_counter() -> None:
    """便捷函数：重置工具调用计数器"""
    _tool_interceptor.reset_counter()


def wrap_tool(tool_func: Callable) -> Callable:
    """装饰器：自动包装 Tool 的调用过程
    
    Usage:
        @wrap_tool
        def my_tool(param1, param2):
            ...
    """
    def wrapper(*args, **kwargs):
        tool_name = tool_func.__name__
        # 合并位置参数和关键字参数
        all_args = {}
        if hasattr(tool_func, '__code__'):
            param_names = tool_func.__code__.co_varnames[:len(args)]
            all_args.update(dict(zip(param_names, args)))
        all_args.update(kwargs)
        
        # 记录调用
        log_tool_call(tool_name, **all_args)
        
        try:
            result = tool_func(*args, **kwargs)
            log_tool_result(result, success=True)
            return result
        except Exception as e:
            log_tool_error(str(e))
            raise
    
    wrapper.__name__ = tool_func.__name__
    wrapper.__doc__ = tool_func.__doc__
    return wrapper
