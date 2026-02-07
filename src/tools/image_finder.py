"""
Image finding and path resolution tools.
Helps locate images and validate paths.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict
from difflib import SequenceMatcher
from langchain.tools import tool
from src.tools.tool_interceptor import log_tool_call, log_tool_step, log_tool_result, log_tool_error


# Common image directories
IMAGE_DIRS = [
    Path(__file__).parent.parent.parent / "inputs",
    Path(__file__).parent.parent.parent / "outputs" / "agent",
    Path(__file__).parent.parent.parent / "outputs" / "alarm",
    Path("/tmp"),
    Path.home(),
]

SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}


@tool
def find_image(query: str, search_dirs: Optional[List[str]] = None) -> str:
    """
    Find image file by query string with fuzzy matching.
    Searches in common directories and returns the best match.
    
    Args:
        query: Image name, partial path, or description (e.g., "camera1", "monitor.jpg", "parking_lot")
        search_dirs: Optional list of additional directories to search
    
    Returns:
        str: Complete absolute path to the image, or error message with suggestions
    """
    try:
        result_lines = []
        result_lines.append(f"🔍 **开始查找图片**")
        result_lines.append(f"📝 查询: '{query}'")
        
        # Prepare search directories
        dirs_to_search = IMAGE_DIRS.copy()
        if search_dirs:
            dirs_to_search.extend([Path(d) for d in search_dirs])
        
        result_lines.append(f"📂 搜索目录 ({len(dirs_to_search)}个):")
        for d in dirs_to_search:
            result_lines.append(f"   - {d}")
        
        # Try direct path first
        result_lines.append(f"\n✨ 步骤1: 尝试直接路径...")
        if os.path.exists(query) and os.path.isfile(query):
            abs_path = os.path.abspath(query)
            result_lines.append(f"✅ 直接匹配成功!")
            result_lines.append(f"📍 路径: {abs_path}")
            return "\n".join(result_lines)
        result_lines.append(f"   未找到直接路径")
        
        # Collect all image files from search directories
        result_lines.append(f"\n✨ 步骤2: 扫描所有图片文件...")
        all_images = {}
        scanned_count = 0
        for search_dir in dirs_to_search:
            if search_dir.exists() and search_dir.is_dir():
                for file in search_dir.rglob("*"):
                    scanned_count += 1
                    if file.is_file() and file.suffix.lower() in SUPPORTED_FORMATS:
                        all_images[file.name.lower()] = str(file.absolute())
        
        result_lines.append(f"   扫描文件: {scanned_count} 个")
        result_lines.append(f"   找到图片: {len(all_images)} 个")
        
        if not all_images:
            result_lines.append(f"\n❌ 搜索目录中没有图片文件")
            return "\n".join(result_lines)
        
        # Fuzzy matching
        query_lower = query.lower()
        
        # Exact match (case-insensitive)
        result_lines.append(f"\n✨ 步骤3: 精确匹配...")
        if query_lower in all_images:
            path = all_images[query_lower]
            result_lines.append(f"✅ 精确匹配成功!")
            result_lines.append(f"📍 路径: {path}")
            return "\n".join(result_lines)
        result_lines.append(f"   未找到精确匹配")
        
        # Partial match
        result_lines.append(f"\n✨ 步骤4: 部分匹配...")
        partial_matches = [
            (name, path) for name, path in all_images.items() 
            if query_lower in name
        ]
        
        if partial_matches:
            result_lines.append(f"   找到 {len(partial_matches)} 个部分匹配")
            best_match = partial_matches[0]
            result_lines.append(f"✅ 最佳匹配:")
            result_lines.append(f"📍 {best_match[1]}")
            if len(partial_matches) > 1:
                result_lines.append(f"\n📋 其他匹配:")
                for name, path in partial_matches[1:4]:
                    result_lines.append(f"   - {path}")
            return "\n".join(result_lines)
        result_lines.append(f"   未找到部分匹配")
        
        # Similarity matching
        result_lines.append(f"\n✨ 步骤5: 相似度匹配...")
        matches = [
            (name, path, SequenceMatcher(None, query_lower, name).ratio())
            for name, path in all_images.items()
        ]
        matches.sort(key=lambda x: x[2], reverse=True)
        
        if matches:
            best_similarity = matches[0][2]
            result_lines.append(f"   最高相似度: {best_similarity:.0%}")
            
            if best_similarity > 0.4:
                result_lines.append(f"✅ 找到相似匹配 (>40%):")
                result_lines.append(f"📍 {matches[0][1]}")
                if len(matches) > 1:
                    result_lines.append(f"\n📋 其他相似匹配:")
                    for name, path, ratio in matches[1:4]:
                        result_lines.append(f"   - {path} ({ratio:.0%})")
                return "\n".join(result_lines)
        
        # No matches
        result_lines.append(f"\n❌ 未找到匹配的图片")
        result_lines.append(f"\n📁 可用的图片 (前10个):")
        for i, (name, path) in enumerate(list(all_images.items())[:10], 1):
            result_lines.append(f"   {i}. {name}")
        if len(all_images) > 10:
            result_lines.append(f"   ... 还有 {len(all_images) - 10} 个")
        
        return "\n".join(result_lines)
    
    except Exception as e:
        return f"❌ 查找图片时出错: {str(e)}"


@tool
def list_images(directory: str = "inputs", pattern: Optional[str] = None) -> str:
    """
    List all available images in a specific directory.
    
    Args:
        directory: Directory name ('inputs', 'outputs', or full path)
        pattern: Optional pattern to filter images (e.g., 'camera*', '*.jpg')
    
    Returns:
        str: Formatted list of available images with their full paths
    """
    try:
        # Resolve directory path
        if directory == "inputs":
            target_dir = Path(__file__).parent.parent.parent / "inputs"
        elif directory == "outputs":
            target_dir = Path(__file__).parent.parent.parent / "outputs" / "agent"
        else:
            target_dir = Path(directory)
        
        if not target_dir.exists():
            return f"❌ Directory not found: {target_dir}"
        
        if not target_dir.is_dir():
            return f"❌ Path is not a directory: {target_dir}"
        
        # Find images
        images = []
        for file in target_dir.rglob("*"):
            if file.is_file() and file.suffix.lower() in SUPPORTED_FORMATS:
                # Apply pattern filter if provided
                if pattern:
                    if not _matches_pattern(file.name, pattern):
                        continue
                images.append(file)
        
        if not images:
            return f"❌ No images found in {target_dir}"
        
        # Format output
        result = f"📁 Images in {target_dir.name}/ ({len(images)} total):\n\n"
        for i, img_path in enumerate(sorted(images), 1):
            rel_path = img_path.relative_to(target_dir.parent)
            result += f"{i}. {rel_path}\n"
            result += f"   Full path: {img_path.absolute()}\n"
        
        return result
    
    except Exception as e:
        return f"❌ Error listing images: {str(e)}"


@tool
def validate_image(path: str) -> str:
    """
    Validate if an image path exists and is readable.
    
    Args:
        path: Image file path to validate
    
    Returns:
        str: Validation result with file info
    """
    try:
        file_path = Path(path)
        
        if not file_path.exists():
            return f"❌ File does not exist: {path}"
        
        if not file_path.is_file():
            return f"❌ Path is not a file: {path}"
        
        if file_path.suffix.lower() not in SUPPORTED_FORMATS:
            return f"❌ Not a supported image format: {file_path.suffix}\nSupported: {', '.join(SUPPORTED_FORMATS)}"
        
        # Check if readable
        if not os.access(file_path, os.R_OK):
            return f"❌ File is not readable: {path}"
        
        # Get file info
        stat_info = file_path.stat()
        size_mb = stat_info.st_size / (1024 * 1024)
        
        result = f"✅ Valid image file\n\n"
        result += f"📄 **File Info:**\n"
        result += f"  - Path: {file_path.absolute()}\n"
        result += f"  - Size: {size_mb:.2f} MB\n"
        result += f"  - Format: {file_path.suffix.lower()}\n"
        
        return result
    
    except Exception as e:
        return f"❌ Error validating image: {str(e)}"


def _matches_pattern(filename: str, pattern: str) -> bool:
    """Check if filename matches a wildcard pattern."""
    import fnmatch
    return fnmatch.fnmatch(filename.lower(), pattern.lower())
