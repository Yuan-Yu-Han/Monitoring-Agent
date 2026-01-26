from langgraph.graph import StateGraph, END
from detection_agent.state import AgentState
from detection_agent.tools import detect_image, safe_parse_json, draw_bboxes

def build_graph():
    """
    构建状态图graph
    """
    graph = StateGraph(AgentState)

    # 节点创建
    graph.add_node("detect", detect_image)
    graph.add_node("parse", safe_parse_json)
    graph.add_node("draw", draw_bboxes)
    graph.set_entry_point("detect")

    # 边创建
    graph.add_edge("detect", "parse")
    graph.add_edge("parse", "draw")
    graph.add_edge("draw", END)

    return graph.compile()