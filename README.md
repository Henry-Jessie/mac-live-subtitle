# Deepgram 实时字幕

[English](./README_EN.md) | 中文

为 macOS 提供超低延迟的系统音频实时转录和翻译，带浮动字幕窗口。

## 功能特点

- **超低延迟转录** 使用 Deepgram 的流式 API（<500ms）
- **实时中文翻译** 支持上下文感知
- **浮动字幕窗口** 始终保持在其他应用程序之上
- **自动语言检测** （中文、日文、英文等）
- **智能字幕润色** 带错误纠正功能
- **可调整字幕窗口** 支持自定义外观
- **自动重连** 连接失败时自动重新连接

## 工作原理

### Deepgram 流式语音识别

Deepgram 提供实时自动语音识别（ASR）。客户端通过 WebSocket 将短音频帧流式传输到 Deepgram 云端，并在几百毫秒内收到相应的转录文本。本项目只需将捕获的系统音频转发给 Deepgram 并渲染返回的字幕——无需本地语音转文本模型。

#### Deepgram Nova-3 Multi 定价
- 实时流式转录：$0.0092/分钟（$0.552/小时）
- 支持多语言自动检测（中文、日文、英文等）
- $200 免费额度可使用约 362 小时


### BlackHole 虚拟音频设备

BlackHole 是一个基于 Core Audio DriverKit 构建的 macOS 开源虚拟音频驱动程序。它分配了一个内核空间的**环形缓冲区**，该缓冲区既作为输出端点（操作系统写入 PCM 样本）又作为输入端点（捕获应用程序可以读取）。

通过在音频 MIDI 设置中创建**多输出设备**，系统音频会同时镜像到物理扬声器和 BlackHole。`audio_capture.py` 模块打开 BlackHole 的输入端点，获取 48 kHz 立体声流，将其降采样为 16 kHz 单声道，并流式传输到 Deepgram——实现无需硬件、近乎零延迟的系统音频捕获。

### 智能翻译与润色

翻译系统分两个阶段工作：

1. **实时转录**：Deepgram 提供临时（部分）和最终转录结果。临时结果在音频捕获时持续更新，提供即时的视觉反馈。

2. **上下文感知翻译**：
   - 当 Deepgram 将片段标记为"最终"或连续语音超过 1 秒时触发翻译
   - 润色模型（可配置，默认：通过 OpenRouter 的 Gemini 2.5 Flash）接收转录文本和最近的上下文
   - 模型同时执行三项任务：
     - **错误纠正**：修复常见的 ASR 错误（例如："P vs MP" → "P vs NP"）
     - **上下文增强**：使用对话历史提高准确性
     - **翻译**：生成自然的中文翻译，同时保留技术术语
   
3. **显示逻辑**：
   - 原文随每个临时结果实时更新
   - 中文翻译保持稳定，只在收到新翻译时更新
   - 检测到静音一段时间后（DeepGram传输空字符），窗口会自动隐藏

## 系统要求

- macOS（在 macOS 15.5 上测试）
- Python 3.10+
- BlackHole 虚拟音频设备（用于系统音频捕获）
- Deepgram API 密钥
- OpenRouter API 密钥（或其他 LLM 提供商用于翻译）

## 安装步骤

### 1. 安装依赖项

通过 Homebrew 安装所需的系统依赖：

```bash
# 安装 BlackHole 用于音频捕获
brew install blackhole-2ch

# 安装 Python tkinter（如果尚未安装）
brew install python-tk
```

或从以下地址下载 BlackHole：https://existential.audio/blackhole/

### 2. 克隆仓库

```bash
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git
cd mac-live-subtitle
```

### 3. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. 安装依赖包

```bash
pip install -r requirements.txt
```

### 5. 配置 API 密钥

在项目根目录创建 `.env` 文件：

```bash
# 必需
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# 用于翻译（选择其一）
OPENROUTER_API_KEY=your_openrouter_api_key_here
# 或直接使用 OpenAI
OPENAI_API_KEY=your_openai_api_key_here
```

获取 API 密钥：
- Deepgram：https://console.deepgram.com/
- OpenRouter：https://openrouter.ai/
- OpenAI：https://platform.openai.com/

### 6. 配置音频路由

1. 打开**音频 MIDI 设置**（位于 /应用程序/实用工具/）
2. 点击左下角的"+"按钮，选择"创建多输出设备"
3. 勾选"BlackHole 2ch"和您的常规输出设备（例如"MacBook Pro 扬声器"）。将顶部的主设备设置为实际输出设备（例如"MacBook Pro 扬声器"），而不是"BlackHole 2ch"
4. 设置采样率为 48.0 kHz（这是默认采样率，大多数情况下无需更改）
5. 右键点击多输出设备，选择"将此设备用于声音输出"

这样可以让您在应用程序捕获音频的同时正常听到声音。

## 配置

编辑 `config/config.yaml` 进行自定义：

```yaml
# 音频设置
audio:
  device_name: "BlackHole 2ch"  # 虚拟音频设备名称
  sample_rate: 16000
  channels: 1
  chunk_duration: 0.5
  buffer_size: 2048

# Deepgram 设置
deepgram:
  model: "nova-3"  # 实时转录的最佳模型
  language: "multi"  # 自动检测 zh/ja/en
  interim_results: true  # 显示部分结果
  
  # 翻译模型设置
  polish:
    model: "google/gemini-2.5-flash"  # 快速准确
    api_key_env: "OPENROUTER_API_KEY"  # 使用哪个环境变量
    base_url: "https://openrouter.ai/api/v1"

# 显示设置
display:
  window_width: 800
  window_height: 150
  window_opacity: 0.9
  always_on_top: true
  position_y_offset: 100  # 距离底部的距离
  resizable: true  # 允许调整窗口大小
  
  # 字体设置
  original_font:
    family: "Arial"        # 原文字体
    size: 22              # 字体大小
    color: "#FFFFFF"      # 白色
    
  chinese_font:
    family: "PingFang SC" # 中文字体（macOS）
    size: 20              # 字体大小
    color: "#FFFF00"      # 黄色
```

查看 `config/config.yaml` 获取完整配置选项。

## 使用方法

### 基本使用

```bash
python main.py
```

### 命令行选项

```bash
# 列出可用的音频设备
python main.py --list-devices

# 使用不同的音频设备
python main.py --device "Your Device Name"

# 使用不同的配置文件
python main.py --config path/to/config.yaml
```

### 键盘快捷键

- **拖动窗口**：点击并拖动字幕窗口来重新定位
- **调整窗口大小**：拖动窗口边缘（如果启用了 resizable）
- **隐藏窗口**：当窗口获得焦点时按 `Esc`
- **退出**：在终端中按 `Ctrl+C`

## 项目结构

```
gemini-live-subtitle/
├── main.py                      # 主应用程序入口
├── requirements.txt             # Python 依赖
├── config/
│   └── config.yaml              # 主配置文件
├── src/
│   ├── audio_capture.py         # macOS 音频捕获模块
│   ├── deepgram_transcriber.py  # Deepgram 流式转录
│   └── subtitle_display.py      # 字幕窗口 UI
├── tests/                       # 测试工具
│   ├── test_audio_capture.py    # 音频捕获测试
│   ├── test_deepgram_transcriber.py  # 转录管道测试
│   └── test_window.py           # 字幕窗口测试
└── logs/
    └── subtitle.log             # 应用程序日志
```

## 故障排除

### 没有捕获到音频

1. 检查 BlackHole 是否已安装并在音频 MIDI 设置中可见
2. 确保您的多输出设备同时包含 BlackHole 和扬声器
3. 运行 `python main.py --list-devices` 验证 BlackHole 是否被检测到

### 字幕未出现

1. 检查 `logs/subtitle.log` 中的错误
2. 验证您的 API 密钥是否正确设置在 `.env` 中
3. 确保字幕窗口没有隐藏在其他窗口后面

### 高延迟或延迟

1. 检查您的互联网连接
2. 考虑在配置中使用更快的翻译模型
3. 减少音频设置中的 `chunk_duration`（可能会增加 CPU 使用率）

### WebSocket 连接错误

应用程序会在连接失败时自动重连。如果问题持续：
1. 检查您的 Deepgram API 密钥是否有效
2. 验证您的互联网连接是否稳定
3. 检查 Deepgram 服务状态

### 测试工具

`tests/` 目录包含帮助诊断问题的工具：

#### 1. **test_audio_capture.py** - 测试系统音频捕获
```bash
python tests/test_audio_capture.py
```
- 测试 BlackHole 是否正确配置并接收音频
- 显示实时音量级别和音频统计信息
- 将 48kHz 立体声输入转换为 16kHz 单声道输出
- 使用场景：音频未被捕获或看不到音量活动

#### 2. **test_deepgram_transcriber.py** - 测试转录管道
```bash
python tests/test_deepgram_transcriber.py
```
- 测试完整的转录和翻译管道
- 显示实时转录（临时结果）和中文翻译
- 验证 Deepgram API 连接和润色模型功能
- 使用场景：转录不工作或翻译未出现

#### 3. **test_window.py** - 测试字幕显示窗口
```bash
python tests/test_window.py

# 测试可调整大小的窗口
python tests/test_window.py --resizable

# 测试不可调整大小的窗口
python tests/test_window.py --no-resizable

# 禁用调试输出
python tests/test_window.py --no-debug

# 测试自定义字体大小
python tests/test_window.py --font-size 30
```
- 测试字幕窗口是否正确显示
- 显示中英文测试消息和长文本换行
- 验证窗口定位、更新和调整大小功能
- 输出窗口尺寸和 wraplength 调试信息
- 使用场景：字幕窗口未出现、未正确更新或调整大小时出现问题

## 许可证

MIT 许可证 - 详见 LICENSE 文件