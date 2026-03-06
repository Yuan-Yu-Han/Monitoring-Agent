"""
Report generation tools for monitoring analysis.
Supports multiple formats (Markdown, JSON, HTML) and storage options.
"""

import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
from langchain.tools import tool


# Output directory configuration
REPORTS_DIR = Path(__file__).parent.parent.parent / "outputs" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


@tool
def generate_report(
    detections: str,
    analysis: str,
    severity: str = "info",
    format: str = "markdown",
    save_file: bool = True,
    region: str = "default",
) -> str:
    """
    Generate a monitoring report based on detections and analysis.

    Args:
        detections: JSON string with detection results or formatted detection text
        analysis: AI analysis and insights from the monitoring system
        severity: Alert severity level (info, warning, critical)
        format: Report format - 'markdown', 'json', or 'html'
        save_file: Whether to save the report to a file
        region: Monitored region/location name

    Returns:
        str: Either full report (if format='json'/'html') or summary with file path info
    """
    try:
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        timestamp_file = timestamp.strftime("%Y%m%d_%H%M%S")

        detections_parsed = _parse_detections(detections)

        if format.lower() == "markdown":
            report_content = _generate_markdown_report(
                detections_parsed, analysis, severity, region, timestamp_str
            )
        elif format.lower() == "json":
            report_content = _generate_json_report(
                detections_parsed, analysis, severity, region, timestamp_str
            )
        elif format.lower() == "html":
            report_content = _generate_html_report(
                detections_parsed, analysis, severity, region, timestamp_str
            )
        else:
            return f"❌ Unsupported format: {format}. Use 'markdown', 'json', or 'html'."

        file_path = None
        if save_file:
            file_path = _save_report(report_content, format, region, timestamp_file)

        summary = _generate_summary(
            detections_parsed, analysis, severity, format, file_path
        )
        return summary

    except Exception as e:
        raise


def _parse_detections(detections: Any) -> Dict[str, Any]:
    """Parse detections from string or dict format."""
    if isinstance(detections, str):
        try:
            return json.loads(detections)
        except json.JSONDecodeError:
            # If not valid JSON, treat as plain text
            return {"raw": detections}
    elif isinstance(detections, dict):
        return detections
    else:
        return {"raw": str(detections)}


def _generate_markdown_report(
    detections: Dict,
    analysis: str,
    severity: str,
    region: str,
    timestamp: str,
) -> str:
    """Generate Markdown format report."""
    severity_icon = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }.get(severity.lower(), "📋")

    report = f"""# 监控分析报告

**生成时间：** {timestamp}  
**监控区域：** {region}  
**严重程度：** {severity_icon} {severity.upper()}

---

## 检测结果

"""
    
    if isinstance(detections, dict):
        if "detections" in detections and isinstance(detections["detections"], list):
            report += f"**总检测数量：** {len(detections['detections'])}\n\n"
            for idx, det in enumerate(detections["detections"], 1):
                if isinstance(det, dict):
                    label = det.get("class", f"Object {idx}")
                    conf = det.get("confidence", "N/A")
                    report += f"- {label}: {conf}\n"
                else:
                    report += f"- {det}\n"
        elif "raw" in detections:
            report += f"{detections['raw']}\n"
        else:
            report += json.dumps(detections, indent=2, ensure_ascii=False) + "\n"
    else:
        report += str(detections) + "\n"
    
    report += f"""
---

## AI 分析

{analysis}

---

## 建议

"""
    
    if severity.lower() == "critical":
        report += "- 立即采取行动，联系相关人员\n"
        report += "- 保存监控录像以供后续审查\n"
    elif severity.lower() == "warning":
        report += "- 加强监控和观察\n"
        report += "- 记录事件并保存日志\n"
    else:
        report += "- 继续正常监控\n"
        report += "- 定期查阅报告\n"
    
    return report


def _generate_json_report(
    detections: Dict,
    analysis: str,
    severity: str,
    region: str,
    timestamp: str,
) -> str:
    """Generate JSON format report."""
    report_dict = {
        "metadata": {
            "timestamp": timestamp,
            "region": region,
            "severity": severity,
            "report_type": "monitoring_analysis",
        },
        "detections": detections,
        "analysis": analysis,
        "recommendations": _get_recommendations(severity),
    }
    
    return json.dumps(report_dict, indent=2, ensure_ascii=False)


def _generate_html_report(
    detections: Dict,
    analysis: str,
    severity: str,
    region: str,
    timestamp: str,
) -> str:
    """Generate HTML format report."""
    severity_color = {
        "info": "#0066cc",
        "warning": "#ff9900",
        "critical": "#cc0000",
    }.get(severity.lower(), "#333333")
    
    detections_html = _dict_to_html_table(detections)
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>监控分析报告</title>
    <style>
        body {{
            font-family: "Microsoft YaHei", Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid {severity_color};
            padding-bottom: 10px;
        }}
        .metadata {{
            background-color: #f9f9f9;
            padding: 15px;
            border-left: 4px solid {severity_color};
            margin: 20px 0;
            border-radius: 4px;
        }}
        .severity-badge {{
            display: inline-block;
            background-color: {severity_color};
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            margin-left: 10px;
        }}
        .section {{
            margin: 25px 0;
        }}
        .section h2 {{
            color: {severity_color};
            border-bottom: 1px solid #ddd;
            padding-bottom: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }}
        th {{
            background-color: {severity_color};
            color: white;
        }}
        .analysis {{
            background-color: #f0f8ff;
            padding: 15px;
            border-radius: 4px;
            line-height: 1.6;
        }}
        .recommendations {{
            background-color: #fffacd;
            padding: 15px;
            border-radius: 4px;
        }}
        .recommendations ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .footer {{
            text-align: center;
            color: #999;
            margin-top: 30px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>监控分析报告 <span class="severity-badge">{severity.upper()}</span></h1>
        
        <div class="metadata">
            <p><strong>生成时间：</strong> {timestamp}</p>
            <p><strong>监控区域：</strong> {region}</p>
            <p><strong>严重程度：</strong> {severity.upper()}</p>
        </div>
        
        <div class="section">
            <h2>检测结果</h2>
            {detections_html}
        </div>
        
        <div class="section">
            <h2>AI 分析</h2>
            <div class="analysis">
                {analysis}
            </div>
        </div>
        
        <div class="section">
            <h2>建议</h2>
            <div class="recommendations">
                <ul>
                    {''.join([f'<li>{rec}</li>' for rec in _get_recommendations(severity)])}
                </ul>
            </div>
        </div>
        
        <div class="footer">
            <p>本报告由智能监控系统自动生成</p>
        </div>
    </div>
</body>
</html>"""
    
    return html


def _dict_to_html_table(data: Dict) -> str:
    """Convert detection dict to HTML table."""
    if not isinstance(data, dict):
        return f"<p>{str(data)}</p>"
    
    if "detections" in data and isinstance(data["detections"], list):
        html = "<table><tr><th>类型</th><th>置信度</th><th>坐标</th></tr>"
        for det in data["detections"]:
            if isinstance(det, dict):
                label = det.get("class", "Unknown")
                conf = det.get("confidence", "N/A")
                coords = det.get("box", "N/A")
                html += f"<tr><td>{label}</td><td>{conf}</td><td>{coords}</td></tr>"
        html += "</table>"
        return html
    else:
        return f"<pre>{json.dumps(data, indent=2, ensure_ascii=False)}</pre>"


def _save_report(
    content: str, 
    format: str, 
    region: str, 
    timestamp: str
) -> str:
    """Save report to file and return file path."""
    # Create region-specific subdirectory
    region_dir = REPORTS_DIR / region.replace(" ", "_")
    region_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine file extension
    ext = {
        "markdown": "md",
        "json": "json",
        "html": "html",
    }.get(format.lower(), "txt")
    
    # Create file path
    filename = f"report_{timestamp}.{ext}"
    file_path = region_dir / filename
    
    # Write file
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(file_path)
    except Exception as e:
        print(f"Warning: Failed to save report file: {e}")
        return None


def _get_recommendations(severity: str) -> List[str]:
    """Get recommendations based on severity level."""
    recommendations = {
        "critical": [
            "立即采取行动，联系相关人员",
            "保存监控录像以供后续审查",
            "记录详细事件日志",
            "启动应急响应流程",
        ],
        "warning": [
            "加强监控和观察",
            "记录事件并保存日志",
            "准备随时采取行动",
            "通知相关监管人员",
        ],
        "info": [
            "继续正常监控",
            "定期查阅报告",
            "维护完整日志记录",
            "参考历史数据进行分析",
        ],
    }
    
    return recommendations.get(severity.lower(), recommendations["info"])


def _generate_summary(
    detections: Dict,
    analysis: str,
    severity: str,
    format: str,
    file_path: Optional[str],
) -> str:
    """Generate concise summary for dialogue display."""
    severity_emoji = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }.get(severity.lower(), "📋")
    
    summary = f"{severity_emoji} **报告已生成** ({format.upper()})\n\n"
    
    # Count detections
    if isinstance(detections, dict):
        if "detections" in detections and isinstance(detections["detections"], list):
            count = len(detections["detections"])
            summary += f"📊 **检测数量：** {count}\n"
    
    # Add first line of analysis
    first_line = analysis.split("\n")[0][:100]
    summary += f"💡 **分析摘要：** {first_line}...\n"
    
    # Add file info if saved
    if file_path:
        summary += f"\n✅ **报告已保存：** {file_path}"
    
    return summary
