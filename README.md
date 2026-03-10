# OCR Flow

将 PDF 文档（芯片手册、数据手册）转换为 AI 可读的 Markdown 格式的命令行工具。

## 功能特性

- **PDF 类型检测** - 自动识别文字版或扫描版 PDF
- **OCR 支持** - 通过 UMI OCR 处理扫描文档
- **PDF 翻译** - 使用 BabelDOC 翻译 PDF 为中文
- **PDF 压缩** - 使用 Ghostscript 减小文件体积
- **Markdown 转换** - 通过 MinerU API 提取结构化内容
- **图片本地化** - 下载并本地化远程图片
- **状态管理** - 支持中断后恢复/重试

## 安装

### 前置要求

1. **Python 3.9+**
2. **Ghostscript** - [下载地址](https://ghostscript.com/)
3. **UMI OCR**（可选，用于扫描版 PDF）- [下载地址](https://github.com/hiroi-sora/Umi-OCR/releases)
4. **BabelDOC**（可选，用于翻译）- [安装指南](https://github.com/funstory-ai/BabelDOC)

### 安装 OCR Flow

```bash
cd ocr_flow
uv venv
uv pip install -e .
```

### 安装可选依赖

```bash
# .NET WebClient（Windows 下更好的 SSL 兼容性）
uv pip install pythonnet

# 单元测试
uv pip install -e ".[dev]"
```

## 配置

运行交互式配置向导：

```bash
ocr-flow config
```

或手动创建 `~/.ocr-flow/config.toml`：

```toml
[mineru]
api_token = "你的-mineru-api-token"

[babeldoc]
path = "../BabelDOC"  # BabelDOC git 仓库路径（可选）
lang_in = "en-US"
lang_out = "zh-CN"
openai = true
openai_model = "qwen3.5-flash"
openai_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
openai_api_key = "sk-xxx"

[umiocr]
url = "http://127.0.0.1:1224"
language = "models/config_en.txt"

[compress]
ghostscript_path = ""  # 留空则自动检测
quality = "ebook"
```

## 使用方法

### 基本处理

```bash
# 处理文字版 PDF
ocr-flow process input.pdf -o output/ --non-interactive --pdf-type text --lang en --no-translate -v

# 自动检测 PDF 类型
ocr-flow process input.pdf -o output/ --non-interactive --pdf-type auto --lang en --no-translate -v
```

### 带翻译

```bash
# 翻译为中文
ocr-flow process input.pdf -o output/ --non-interactive --pdf-type text --lang en --translate -v
```

### 扫描版 PDF

```bash
# 处理扫描文档（需要 UMI OCR 服务运行中）
ocr-flow process scanned.pdf -o output/ --non-interactive --pdf-type scanned --lang en --no-translate -v
```

### 系统检查

```bash
# 基础检查
ocr-flow doctor

# 检查翻译依赖
ocr-flow doctor --translate

# 检查 OCR 依赖
ocr-flow doctor --ocr
```

## 处理流程

```
输入 PDF
    │
    ├─► [OCR]（如果是扫描版）─► 文字 PDF
    │
    ├─► [翻译]（如果启用）─► 双语 PDF
    │
    ├─► [分割] ─► 单页块
    │
    ├─► [压缩] ─► 更小的 PDF
    │
    ├─► [MinerU API] ─► Markdown
    │
    ├─► [格式修复] ─► 整洁的 Markdown
    │
    └─► [图片下载] ─► 本地化图片
         │
         ▼
    输出: part_001.md, part_002.md, ...
```

## 输出结构

```
output/
└── 20260311_120000/
    └── 输入文件名/
        ├── .state.json          # 状态文件（用于恢复/重试）
        ├── .backup/             # 中间文件备份
        ├── intermediate/        # 处理中间产物
        │   ├── split/
        │   ├── compressed/
        │   └── mineru_md/
        └── final/               # 最终输出
            ├── part_001.md
            ├── part_002.md
            ├── images/
            └── compressed_pdfs/
```

## 开发

### 运行测试

```bash
pytest tests/ -v
```

### 创建测试 PDF

```bash
python create_stress_test_pdf.py
```

## API Token 获取

- **MinerU API**: 从 [MinerU 官网](https://mineru.net/) 获取
- **OpenAI 兼容 API**: 用于 BabelDOC 翻译（如通义千问、DeepSeek）

## 常见问题

### SSL 下载错误

如果从 MinerU CDN 下载时遇到 SSL 错误：

1. 安装 `pythonnet`: `uv pip install pythonnet`
2. 工具会自动使用 .NET WebClient 作为备选方案

### 找不到 UMI OCR

1. 从 [GitHub](https://github.com/hiroi-sora/Umi-OCR/releases) 下载 UMI OCR
2. 启动应用程序（会在 `127.0.0.1:1224` 运行 HTTP API）

### 找不到 BabelDOC

```bash
git clone https://github.com/funstory-ai/BabelDOC.git
cd BabelDOC
uv venv
uv pip install -e .
```

## 许可证

MIT
