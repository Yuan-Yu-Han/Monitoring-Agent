#!/usr/bin/env python3
"""
处理单个视频文件的脚本
用法: python scripts/process_single_video.py <video_file_path>
"""

import os
import sys
import subprocess
from glob import glob
from pathlib import Path
from config import CONFIG

def is_video_already_processed(video_path, output_dir):
    """
    检查视频是否已经处理过
    """
    video_path = Path(video_path)
    video_name = video_path.stem
    video_output_dir = os.path.join(output_dir, video_name)
    
    # 检查输出目录是否存在且不为空
    if os.path.exists(video_output_dir):
        # 检查是否有jpg文件
        jpg_files = glob(os.path.join(video_output_dir, "*.jpg"))
        if jpg_files:
            # 检查视频文件修改时间是否早于图片文件
            video_mtime = os.path.getmtime(video_path)
            newest_image_mtime = max(os.path.getmtime(f) for f in jpg_files)
            
            # 如果视频文件没有更新，且已有图片文件，则认为已处理
            if video_mtime <= newest_image_mtime:
                return True, video_output_dir, len(jpg_files)
    
    return False, video_output_dir, 0

def process_video_to_images(video_path):
    """
    将单个视频文件转换为图片序列
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        print(f"❌ 错误: 视频文件不存在: {video_path}")
        return None
    
    video_name = video_path.stem  # 获取不带扩展名的文件名
    output_dir = CONFIG["io"]["input_dir"]
    
    # 检查是否已经处理过
    already_processed, video_output_dir, image_count = is_video_already_processed(video_path, output_dir)
    
    if already_processed:
        print(f"✅ 视频已处理过: {video_path}")
        print(f"   输出目录: {video_output_dir}")
        print(f"   图片数量: {image_count}")
        print(f"   如需重新处理，请删除目录: {video_output_dir}")
        return video_output_dir
    
    # 创建同名子文件夹
    os.makedirs(video_output_dir, exist_ok=True)
    
    # 构建ffmpeg命令
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", "fps=1/0.5",  # 每0.5秒一帧
        "-q:v", "2",  # 高质量
        os.path.join(video_output_dir, "%06d.jpg"),
        "-y"  # 覆盖已存在文件
    ]
    
    print(f"🎬 正在处理视频: {video_path}")
    print(f"   输出目录: {video_output_dir}")
    print(f"   命令: {' '.join(cmd)}")
    
    try:
        # 执行ffmpeg命令
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ 视频处理完成: {video_path}")
        
        # 统计生成的图片数量
        image_count = len([f for f in os.listdir(video_output_dir) if f.endswith('.jpg')])
        print(f"   生成了 {image_count} 张图片")
        
        return video_output_dir
    except subprocess.CalledProcessError as e:
        print(f"❌ 视频处理失败: {e}")
        print(f"   错误输出: {e.stderr}")
        return None
    except FileNotFoundError:
        print("❌ 错误: 未找到ffmpeg，请先安装ffmpeg")
        print("   Ubuntu/Debian: sudo apt install ffmpeg")
        print("   CentOS/RHEL: sudo yum install ffmpeg")
        print("   macOS: brew install ffmpeg")
        return None

def main():
    if len(sys.argv) != 2:
        print("用法: python scripts/process_single_video.py <video_file_path>")
        print("示例: python scripts/process_single_video.py ./videos/fire_demo.mp4")
        sys.exit(1)
    
    video_path = sys.argv[1]
    result = process_video_to_images(video_path)
    
    if result:
        print(f"✅ 成功! 图片保存在: {result}")
        print(f"现在可以运行: python main.py")
    else:
        print("❌ 处理失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
