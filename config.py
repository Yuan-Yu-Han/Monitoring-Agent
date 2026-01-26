import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent / ".env" # .env 文件与 config.py 在同一目录
load_dotenv(dotenv_path=env_path)


@dataclass
class OpenAIConfig:
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    max_tokens: int = 2000
    temperature: float = 0.1
    timeout: int = 30
    max_retries: int = 3


@dataclass
class VLLMConfig:
    base_url: str = "http://127.0.0.1:8000/v1"
    model_name: str = "Qwen2.5-VL-7B-Instruct"
    api_key: str = ""
    max_tokens: int = 2000
    temperature: float = 0.1
    timeout: int = 30


@dataclass
class DetectionConfig:
    default_strategy: str = "local_yolo"
    fallback_enabled: bool = True
    auto_fallback: bool = True
    max_concurrent: int = 5


@dataclass
class AgentConfig:
    name: str = "HybridMonitoringAgent"
    max_steps: int = 100
    verbose: bool = True
    memory_size: int = 50
    enable_tools: bool = True
    tools_enabled: List[str] = field(default_factory=lambda: [
        "detect_image",
        "safe_parse_json",
        "draw_bboxes",
        "process_video",
        "generate_report"
    ])


@dataclass
class HybridAgentConfig:
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    vllm: VLLMConfig = field(default_factory=VLLMConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    
    debug: bool = False
    log_level: str = "INFO"
    cache_enabled: bool = True
    cache_dir: str = "./cache"

    def __post_init__(self):
        self._load_from_env()
        if self.cache_enabled:
            os.makedirs(self.cache_dir, exist_ok=True)

    def _load_from_env(self):
        if not self.openai.api_key:
            self.openai.api_key = os.getenv("OPENAI_API_KEY", "")
        if not self.vllm.api_key or self.vllm.api_key == "EMPTY":
            self.vllm.api_key = os.getenv("VLLM_API_KEY", "EMPTY")

        self.openai.model = os.getenv("OPENAI_MODEL", self.openai.model)
        self.vllm.base_url = os.getenv("VLLM_BASE_URL", self.vllm.base_url)
        self.vllm.model_name = os.getenv("VLLM_MODEL_NAME", self.vllm.model_name)

        if os.getenv("HYBRID_AGENT_DEBUG", "").lower() in ("true", "1", "yes"):
            self.debug = True
            self.log_level = "DEBUG"

    def validate(self) -> Dict[str, Any]:
        result = {"valid": True, "errors": [], "warnings": []}

        if not self.openai.api_key:
            result["warnings"].append("OpenAI API密钥未设置，在线API策略将不可用")
        if not self.vllm.api_key or self.vllm.api_key == "EMPTY":
            result["warnings"].append("vLLM API密钥未设置，本地Agent策略可能不可用")

        valid_strategies = ["local_yolo", "qwen_vl", "online_api"]
        if self.detection.default_strategy not in valid_strategies:
            result["errors"].append(f"无效的默认检测策略: {self.detection.default_strategy}")
            result["valid"] = False

        if self.openai.max_tokens <= 0:
            result["errors"].append("OpenAI max_tokens必须大于0")
            result["valid"] = False

        if not (0 <= self.openai.temperature <= 2):
            result["errors"].append("OpenAI temperature必须在0到2之间")
            result["valid"] = False

        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "openai": asdict(self.openai),
            "vllm": asdict(self.vllm),
            "detection": asdict(self.detection),
            "agent": asdict(self.agent),
            "system": {
                "debug": self.debug,
                "log_level": self.log_level,
                "cache_enabled": self.cache_enabled,
                "cache_dir": self.cache_dir
            }
        }

    def save_to_file(self, file_path: str):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, file_path: str) -> "HybridAgentConfig":
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"配置文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def get_section(datadict, key, default):
            return datadict.get(key, default)

        openai_data = get_section(data, "openai", {})
        vllm_data = get_section(data, "vllm", {})
        detection_data = get_section(data, "detection", {})
        agent_data = get_section(data, "agent", {})
        system_data = get_section(data, "system", {})

        return cls(
            openai=OpenAIConfig(**openai_data),
            vllm=VLLMConfig(**vllm_data),
            detection=DetectionConfig(**detection_data),
            agent=AgentConfig(**agent_data),
            debug=system_data.get("debug", False),
            log_level=system_data.get("log_level", "INFO"),
            cache_enabled=system_data.get("cache_enabled", True),
            cache_dir=system_data.get("cache_dir", "./cache")
        )


def load_config() -> HybridAgentConfig:
    """优先从 JSON 文件加载配置，再用环境变量覆盖敏感信息"""
    config_path = Path(__file__).parent/ "hybrid_agent_config.json" # 配置文件与 config.py 在同一目录
    if not config_path.exists():
        print(f"⚠️ 配置文件 {config_path} 不存在，使用默认配置")
        config = HybridAgentConfig()
    else:
        config = HybridAgentConfig.load_from_file(str(config_path))

    # 环境变量覆盖已经在 __post_init__ 内实现，所以这里不用重复做

    return config


def print_config(config: HybridAgentConfig):
    print("=== Hybrid Agent 配置信息 ===")
    print("\n[OpenAI]")
    print(f"  API Key: {'已设置' if config.openai.api_key else '未设置'}")
    print(f"  Model: {config.openai.model}")
    print(f"  Max Tokens: {config.openai.max_tokens}")
    print(f"  Temperature: {config.openai.temperature}")

    print("\n[vLLM]")
    print(f"  Base URL: {config.vllm.base_url}")
    print(f"  Model Name: {config.vllm.model_name}")
    print(f"  API Key: {'已设置' if config.vllm.api_key and config.vllm.api_key != 'EMPTY' else '未设置'}")

    print("\n[Detection]")
    print(f"  Default Strategy: {config.detection.default_strategy}")
    print(f"  Fallback Enabled: {config.detection.fallback_enabled}")
    print(f"  Auto Fallback: {config.detection.auto_fallback}")
    print(f"  Max Concurrent: {config.detection.max_concurrent}")

    print("\n[Agent]")
    print(f"  Name: {config.agent.name}")
    print(f"  Max Steps: {config.agent.max_steps}")
    print(f"  Verbose: {config.agent.verbose}")
    print(f"  Enable Tools: {config.agent.enable_tools}")
    print(f"  Tools Enabled: {', '.join(config.agent.tools_enabled)}")

    print("\n[System]")
    print(f"  Debug: {config.debug}")
    print(f"  Log Level: {config.log_level}")
    print(f"  Cache Enabled: {config.cache_enabled}")
    print(f"  Cache Directory: {config.cache_dir}")




if __name__ == "__main__":
    config = load_config()
    print_config(config)    
    validation = config.validate()
    if validation["valid"]:
        print("\n✅ 配置验证通过")
    else:
        print("\n❌ 配置验证失败，错误如下:")
        for error in validation["errors"]:
            print(f" - {error}")  


'''
在 HybridAgentConfig 类：
__post_init__(self)
dataclass 的特殊方法，实例化后自动调用。这里它会从环境变量加载一些敏感配置（如API Key等），并创建缓存目录（如果启用）。
_load_from_env(self)
具体负责读取环境变量覆盖默认的或JSON里的字段。
validate(self) -> Dict[str, Any]
校验配置是否合法，返回结果包括是否有效、错误列表和警告列表。
to_dict(self) -> Dict[str, Any]
把整个配置实例转成Python字典，方便写入JSON或者打印。
save_to_file(self, file_path: str)
将配置保存为JSON文件。
@classmethod load_from_file(cls, file_path: str) -> HybridAgentConfig
从JSON文件读取配置，构造一个HybridAgentConfig实例。
'''

'''
你这样写多个平行的 @dataclass（OpenAIConfig, VLLMConfig 等）没问题。
然后用一个主配置类 HybridAgentConfig 持有它们的实例（聚合关系），这很合理。
'''