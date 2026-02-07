#!/usr/bin/env python3
"""
将outputs子文件夹中的检测图片合成为mp4视频文件
用法: 
1. 独立执行: python scripts/images_to_video.py [子文件夹名]
2. 在main中调用: from scripts.images_to_video import create_videos_from_outputs
"""

import os
import sys
import subprocess
from pathlib import Path
from glob import glob

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import CONFIG
except ImportError:
    # 如果无法导入config，使用默认配置
    CONFIG = {
        "io": {
            "output_dir": "./outputs"
        }
    }

def create_video_from_images(image_dir, output_video_path, fps=2):
    """
    将图片目录中的所有jpg文件合成为mp4视频
    
    Args:
        image_dir: 图片目录路径
        output_video_path: 输出视频文件路径
        fps: 视频帧率，默认2fps（对应0.5秒采样间隔）
    """
    image_dir = Path(image_dir)
    
    if not image_dir.exists():
        print(f"❌ 图片目录不存在: {image_dir}")
        return False
    
    # 获取所有jpg文件并按名称排序
    jpg_files = sorted(glob(os.path.join(image_dir, "*.jpg")))
    
    if not jpg_files:
        print(f"❌ 目录中没有jpg文件: {image_dir}")
        return False
    
    print(f"🎬 正在创建视频: {output_video_path}")
    print(f"   图片目录: {image_dir}")
    print(f"   图片数量: {len(jpg_files)}")
    print(f"   帧率: {fps}fps")
    
    # 检查文件命名格式，决定使用哪种ffmpeg输入模式
    first_file = Path(jpg_files[0]).name
    print(f"   检测到文件格式: {first_file}")
    
    # 判断文件命名格式
    if first_file.endswith('_yolo_detected.jpg') or first_file.endswith('_qwen_detected.jpg') or first_file.endswith('_gpt_detected.jpg'):
        # 使用通配符模式匹配所有检测结果图片
        input_pattern = os.path.join(image_dir, "*_detected.jpg")
        print(f"   使用检测结果模式: {input_pattern}")
        
        # 构建ffmpeg命令 - 使用通配符模式
        cmd = [
            "ffmpeg",
            "-framerate", str(fps),  # 输入帧率
            "-pattern_type", "glob",  # 启用glob模式
            "-i", input_pattern,  # 输入文件模式
            "-c:v", "libx264",  # 视频编码器
            "-pix_fmt", "yuv420p",  # 像素格式，确保兼容性
            "-r", "30",  # 输出帧率
            str(output_video_path),
            "-y"  # 覆盖已存在文件
        ]
    else:
        # 使用传统的数字序列模式
        input_pattern = os.path.join(image_dir, "%06d.jpg")
        print(f"   使用数字序列模式: {input_pattern}")
        
        # 构建ffmpeg命令 - 使用数字序列模式
        cmd = [
            "ffmpeg",
            "-framerate", str(fps),  # 输入帧率
            "-i", input_pattern,  # 输入文件模式
            "-c:v", "libx264",  # 视频编码器
            "-pix_fmt", "yuv420p",  # 像素格式，确保兼容性
            "-r", "30",  # 输出帧率
            str(output_video_path),
            "-y"  # 覆盖已存在文件
        ]
    
    try:
        # 执行ffmpeg命令
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ 视频创建成功: {output_video_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 视频创建失败: {e}")
        print(f"   错误输出: {e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ 错误: 未找到ffmpeg，请先安装ffmpeg")
        print("   Ubuntu/Debian: sudo apt install ffmpeg")
        print("   CentOS/RHEL: sudo yum install ffmpeg")
        print("   macOS: brew install ffmpeg")
        return False

def create_videos_from_outputs(subfolder_name=None):
    """
    将outputs子文件夹中的检测图片合成为视频
    
    Args:
        subfolder_name: 指定的子文件夹名，如果为None则处理所有子文件夹
    """
    outputs_dir = CONFIG["io"]["output_dir"]
    output_videos_dir = "./output_videos"
    
    # 创建输出视频目录
    os.makedirs(output_videos_dir, exist_ok=True)
    
    if not os.path.exists(outputs_dir):
        print(f"❌ outputs目录不存在: {outputs_dir}")
        return []
    
    print(f"🔍 扫描outputs目录: {outputs_dir}")
    
    # 获取所有子文件夹
    subfolders = []
    if subfolder_name:
        # 处理指定子文件夹
        subfolder_path = os.path.join(outputs_dir, subfolder_name)
        if os.path.exists(subfolder_path) and os.path.isdir(subfolder_path):
            subfolders = [subfolder_path]
        else:
            print(f"❌ 指定的子文件夹不存在: {subfolder_name}")
            return []
    else:
        # 处理所有子文件夹，但排除系统文件夹
        for item in os.listdir(outputs_dir):
            # 跳过隐藏文件夹和系统文件夹
            if item.startswith('.') or item in ['logs', '__pycache__', 'temp', 'cache']:
                continue
                
            item_path = os.path.join(outputs_dir, item)
            if os.path.isdir(item_path):
                subfolders.append(item_path)
    
    if not subfolders:
        print(f"📁 outputs目录中没有子文件夹")
        return []
    
    created_videos = []
    
    for subfolder_path in subfolders:
        subfolder_name = os.path.basename(subfolder_path)
        
        # 检查是否有jpg文件 - 支持imgs子目录结构
        jpg_files = glob(os.path.join(subfolder_path, "*.jpg"))
        
        # 如果主目录没有jpg文件，检查imgs子目录
        if not jpg_files:
            imgs_dir = os.path.join(subfolder_path, "imgs")
            if os.path.exists(imgs_dir):
                jpg_files = glob(os.path.join(imgs_dir, "*.jpg"))
                if jpg_files:
                    # 更新图片目录路径为imgs子目录
                    subfolder_path = imgs_dir
                    print(f"📁 在imgs子目录中找到 {len(jpg_files)} 张图片: {subfolder_name}")
        
        if not jpg_files:
            print(f"⏭️  跳过空文件夹: {subfolder_name}")
            continue
        
        # 生成输出视频文件名
        output_video_path = os.path.join(output_videos_dir, f"{subfolder_name}.mp4")
        
        # 创建视频
        success = create_video_from_images(subfolder_path, output_video_path)
        if success:
            created_videos.append({
                "subfolder": subfolder_name,
                "images_count": len(jpg_files),
                "video_path": output_video_path
            })
    
    # 输出统计信息
    if created_videos:
        print(f"\n📊 视频创建统计:")
        print(f"   成功创建: {len(created_videos)} 个视频")
        for video_info in created_videos:
            print(f"   - {video_info['subfolder']}: {video_info['images_count']} 张图片 → {video_info['video_path']}")
    else:
        print(f"❌ 没有成功创建任何视频")
    
    return created_videos

def main():
    """命令行入口"""
    if len(sys.argv) > 1:
        # 处理指定子文件夹
        subfolder_name = sys.argv[1]
        print(f"🎯 处理指定子文件夹: {subfolder_name}")
        created_videos = create_videos_from_outputs(subfolder_name)
    else:
        # 处理所有子文件夹
        print(f"🎯 处理所有子文件夹")
        created_videos = create_videos_from_outputs(ubfolder_name=fire1)
    
    if created_videos:
        print(f"\n✅ 完成! 共创建了 {len(created_videos)} 个视频文件")
        print(f"📁 视频保存在: ./output_videos/")
    else:
        print(f"\n❌ 没有创建任何视频文件")

if __name__ == "__main__":
    main()
