#!/bin/bash

# 视频采样转图片脚本
# 将videos文件夹下的所有视频文件按0.5秒间隔采样转换为图片

# 设置变量
VIDEOS_DIR="./videos"
OUTPUT_DIR="./inputs"
SAMPLE_INTERVAL=0.5  # 采样间隔（秒）

# 创建输出目录（如果不存在）
mkdir -p "$OUTPUT_DIR"

# 检查videos目录是否存在
if [ ! -d "$VIDEOS_DIR" ]; then
    echo "错误: videos目录不存在: $VIDEOS_DIR"
    exit 1
fi

# 检查是否安装了ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "错误: 未找到ffmpeg，请先安装ffmpeg"
    echo "Ubuntu/Debian: sudo apt install ffmpeg"
    echo "CentOS/RHEL: sudo yum install ffmpeg"
    echo "macOS: brew install ffmpeg"
    exit 1
fi

# 支持的视频格式
VIDEO_EXTENSIONS=("mp4" "avi" "mov" "mkv" "flv" "wmv" "webm" "m4v")

echo "开始处理视频文件..."
echo "输入目录: $VIDEOS_DIR"
echo "输出目录: $OUTPUT_DIR"
echo "采样间隔: ${SAMPLE_INTERVAL}秒"
echo "----------------------------------------"

# 计数器
processed_count=0
total_images=0

# 遍历所有视频文件
for video_file in "$VIDEOS_DIR"/*; do
    # 检查文件是否存在且是文件
    if [ ! -f "$video_file" ]; then
        continue
    fi
    
    # 获取文件扩展名（小写）
    extension=$(echo "${video_file##*.}" | tr '[:upper:]' '[:lower:]')
    
    # 检查是否是支持的视频格式
    is_video=false
    for ext in "${VIDEO_EXTENSIONS[@]}"; do
        if [ "$extension" = "$ext" ]; then
            is_video=true
            break
        fi
    done
    
    if [ "$is_video" = false ]; then
        echo "跳过非视频文件: $(basename "$video_file")"
        continue
    fi
    
    # 获取视频文件名（不含扩展名）
    video_name=$(basename "$video_file" ".$extension")
    
    # 创建该视频的输出子目录
    video_output_dir="$OUTPUT_DIR/$video_name"
    mkdir -p "$video_output_dir"
    
    echo "处理视频: $(basename "$video_file")"
    
    # 使用ffmpeg提取帧
    # -i: 输入文件
    # -vf fps=1/0.5: 设置帧率为每0.5秒一帧（即2fps）
    # -q:v 2: 设置图像质量（1-31，数字越小质量越好）
    # %06d.jpg: 输出文件名格式（6位数字补零）
    ffmpeg -i "$video_file" \
           -vf "fps=1/$SAMPLE_INTERVAL" \
           -q:v 2 \
           "$video_output_dir/%06d.jpg" \
           -y 2>/dev/null
    
    if [ $? -eq 0 ]; then
        # 统计生成的图片数量
        image_count=$(ls -1 "$video_output_dir"/*.jpg 2>/dev/null | wc -l)
        total_images=$((total_images + image_count))
        echo "  ✓ 成功生成 $image_count 张图片到 $video_output_dir"
        processed_count=$((processed_count + 1))
    else
        echo "  ✗ 处理失败: $(basename "$video_file")"
    fi
    
    echo ""
done

echo "----------------------------------------"
echo "处理完成！"
echo "处理视频数量: $processed_count"
echo "生成图片总数: $total_images"
echo "图片保存在: $OUTPUT_DIR"

# 显示输出目录结构
if [ $total_images -gt 0 ]; then
    echo ""
    echo "输出目录结构:"
    find "$OUTPUT_DIR" -type d | sort
fi
