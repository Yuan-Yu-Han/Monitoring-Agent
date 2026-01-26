from typing import TypedDict, List, Dict, Annotated, Sequence
from langchain.schema import BaseMessage
from langgraph.graph import add_messages


class AgentState(TypedDict, total=False):
    input_image: str
    detection_mode: str  # 新增：检测模式选择
    raw_result: str
    detections: List[Dict]
    output_image: str
    messages: Annotated[Sequence[BaseMessage], add_messages]
