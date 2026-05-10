# OCR Flow

将 PDF 文档（芯片手册、数据手册）转换为 AI 可读的 Markdown 格式的命令行工具。

## Quick Start

### 最短成功路径（文字版，不翻译）

```bash
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v
```

### 何时使用哪种模式

- **Interactive mode**：第一次使用、还不确定 PDF 类型或是否翻译时使用

  ```bash
  ocr-flow process <input.pdf> -o <output_dir> -v
  ```

- **Non-interactive mode**：已知参数、要批处理、或希望 AI 直接执行完整命令时使用

  ```bash
  ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v
  ```

### Non-interactive 必需参数

使用 `--non-interactive` 时，必须同时提供：

- `--lang`
- `--translate` 或 `--no-translate`

### 常用完整命令模板

```bash
# 文字版，不翻译
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v

# 文字版，翻译为中文
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --translate -v

# 扫描版，不翻译
ocr-flow doctor --ocr --start-ocr
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type scanned --lang en --no-translate -v

# 扫描版，翻译为中文
ocr-flow doctor --ocr --start-ocr
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type scanned --lang en --translate -v
```

### 常见修正

- 缺少 `--lang`：补上 `--lang en` 或 `--lang zh`
- 缺少 `--translate` / `--no-translate`：明确写出其中一个
- 不确定环境是否完整：先运行 `ocr-flow doctor`
- 扫描版 PDF：先运行 `ocr-flow doctor --ocr --start-ocr`

### 翻译任务的中间产物位置

启用 `--translate` 时，OCR Flow 会先生成双语 PDF，再继续生成 Markdown：

- 双语 PDF：`output/<timestamp>/<stem>/intermediate/*.dual.pdf`
- 最终 Markdown：`output/<timestamp>/<stem>/final/*.md`

如果你的目标只是尽快拿到双语 PDF，不必等 Markdown 全部完成才知道它会出现在哪里。

## 功能特性

- **PDF 类型自动检测** - 智能识别文字版或扫描版 PDF
- **OCR 支持** - 通过 UMI OCR 处理扫描文档
- **PDF 翻译** - 使用 BabelDOC 翻译 PDF 为中文，支持 QPS 限制
- **PDF 压缩** - 使用 Ghostscript 减小文件体积，可选压缩模式
- **Markdown 转换** - 通过 MinerU API 提取结构化内容
- **图片本地化** - 下载并本地化远程图片
- **状态管理** - 支持中断后恢复/重试，非交互模式支持 `--recovery` 参数
- **日志系统** - 自动记录处理过程，10MB 自动轮转
- **批量处理** - 支持目录批量处理

## 安装

### 前置要求

1. **Python 3.9+**
2. **Ghostscript** - [下载地址](https://ghostscript.com/)
3. **pythonnet**（Windows 必需）- 用于解决 MinerU CDN 下载时的 SSL 问题
4. **UMI OCR**（可选，用于扫描版 PDF）- [下载地址](https://github.com/hiroi-sora/Umi-OCR/releases)
5. **BabelDOC**（可选，用于翻译）- [安装指南](https://github.com/funstory-ai/BabelDOC)

### 安装 OCR Flow

```bash
cd ocr_flow
uv venv
uv pip install -e .
```

### 安装 Windows 必需依赖

```bash
# Windows 必需：解决 MinerU CDN 下载时的 SSL 错误
uv pip install pythonnet

# 代理支持（如果使用代理）
uv pip install PySocks
```

### 安装开发依赖

```bash
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
qps = 2  # 翻译 API QPS 限制（推荐最大值: 3）

[umiocr]
url = "http://127.0.0.1:1224"
language = "models/config_en.txt"

[compress]
ghostscript_path = ""  # 留空则自动检测
quality = "ebook"
```

## 测试指南

### 测试文件说明

`test_assets/` 目录提供不同类型的测试 PDF：

| 文件 | 大小 | 类型 | 用途 | 推荐场景 |
|------|------|------|------|----------|
| `true_text_test.pdf` | 490KB | 文字版，15页 | 完整流程测试 | ✅ **首选**，验证基本功能 |
| `true_scanned_test.pdf` | 3.3MB | 扫描版，15页 | OCR测试 | 需 UMI OCR 运行 |
| `test_page_text.pdf` | 1.3KB | 文字版，1页 | 快速验证 | 30秒内完成 |
| `test_page_scanned.pdf` | 31KB | 扫描版，1页 | OCR快速验证 | 需 UMI OCR |
| `stress_test_10pages.pdf` | 1.4MB | 文字版，10页 | 压力测试 | 大文件测试 |

### 快速测试命令

**文字版测试（推荐首选）：**

```bash
ocr-flow process test_assets/true_text_test.pdf -o test_output/ \
  --non-interactive --pdf-type text --lang en --no-translate -v
```

预期结果：约2分钟完成，输出 `test_output/` 目录下 15 个 markdown 文件。

**扫描版测试（需先启动 UMI OCR）：**

```bash
# 先检查/启动 OCR 服务
ocr-flow doctor --ocr --start-ocr

# 再运行扫描版测试
ocr-flow process test_assets/true_scanned_test.pdf -o test_output/ \
  --non-interactive --pdf-type scanned --lang en --no-translate -v
```

预期结果：约5-8分钟完成（取决于 OCR 速度）。

**翻译测试：**

```bash
ocr-flow process test_assets/true_text_test.pdf -o test_output/ \
  --non-interactive --pdf-type text --lang en --translate -v
```

注意：需先配置翻译 API（运行 `ocr-flow config`）。

### 非交互模式必需参数

使用 `--non-interactive` 时，以下参数**必须指定**：

| 参数 | 说明 | 为什么必需 |
|------|------|-----------|
| `--lang` | 文档语言 (`en` 或 `zh`) | 交互模式会询问，非交互模式必须预设 |
| `--translate` 或 `--no-translate` | 翻译选项 | 必须明确是否翻译，不能默认 |

### 常见错误及修正

**错误示例 1：缺少 `--lang`**

```bash
# ❌ 错误命令
ocr-flow process <input.pdf> --non-interactive --no-translate

# 报错信息
Error: --lang is required in non-interactive mode.

# ✅ 修正
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v
```

**错误示例 2：缺少翻译选项**

```bash
# ❌ 错误命令
ocr-flow process <input.pdf> --non-interactive --lang en

# 报错信息
Error: --translate or --no-translate is required in non-interactive mode.

# ✅ 修正
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v
```

**错误示例 3：交互模式 vs 非交互模式混淆**

```bash
# 交互模式：程序会询问 PDF 类型、语言、是否翻译
ocr-flow process <input.pdf> -o <output_dir> -v

# 非交互模式：所有必需参数必须一次写全
ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v
```

## 使用方法

### 基本处理

```bash
# 自动检测 PDF 类型（推荐）
ocr-flow process input.pdf -o output/ --non-interactive --lang en --no-translate -v

# 明确指定文字版 PDF
ocr-flow process input.pdf -o output/ --non-interactive --pdf-type text --lang en --no-translate -v
```

### 带翻译

```bash
# 翻译为中文
ocr-flow process input.pdf -o output/ --non-interactive --pdf-type text --lang en --translate -v
```

### 翻译后压缩

翻译后的 PDF 默认不压缩（保留字体子集化，文件较小）。如需压缩，使用 `--compress` 选项：

```bash
# 翻译并压缩（禁用字体子集化以兼容 Ghostscript）
ocr-flow process input.pdf -o output/ --non-interactive --pdf-type text --lang en --translate --compress -v
```

**两种模式对比：**

| 模式 | 命令 | 文件大小 | 说明 |
|------|------|---------|------|
| 默认 | `--translate` | 较小 | 字体子集化，不压缩 |
| 压缩 | `--translate --compress` | 最小 | 禁用子集化，Ghostscript 压缩 |

### 扫描版 PDF

```bash
# 处理扫描文档（需要 UMI OCR 服务运行中）
ocr-flow process scanned.pdf -o output/ --non-interactive --pdf-type scanned --lang en --no-translate -v

# 检查并自动启动 UMI OCR
ocr-flow doctor --ocr --start-ocr
```

### 系统检查

```bash
# 基础检查
ocr-flow doctor

# 检查翻译依赖
ocr-flow doctor --translate

# 检查 OCR 依赖
ocr-flow doctor --ocr

# 检查并自动启动 UMI OCR
ocr-flow doctor --ocr --start-ocr
```

### 批量处理

```bash
# 处理目录下所有 PDF
ocr-flow process ./documents/ -o output/ -v

# 非交互模式批量处理
ocr-flow process ./documents/ -o output/ --non-interactive --pdf-type auto --lang en --no-translate -v
```

### 恢复/重试

如果处理中断，再次运行会自动检测未完成任务并提供恢复选项：

```
[*] 检测到上次未完成的任务:
   步骤: mineru
   [OK] 已完成: 82/87
   [X] 失败: part_004, part_052

   (1) 继续 - 处理未开始的
   (2) 重试失败 - 只处理失败的
   (3) 继续 + 重试
   (4) 重来
   (5) 取消
```

**非交互模式恢复选项：**

```bash
# 自动继续未完成的任务
ocr-flow process input.pdf -o output/ --non-interactive --recovery continue -v

# 只重试失败的任务
ocr-flow process input.pdf -o output/ --non-interactive --recovery retry -v

# 继续 + 重试失败
ocr-flow process input.pdf -o output/ --non-interactive --recovery continue_retry -v

# 重新开始
ocr-flow process input.pdf -o output/ --non-interactive --recovery restart -v
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
        ├── final/               # 最终输出
        │   ├── part_001.md
        │   ├── part_002.md
        │   ├── images/
        │   └── compressed_pdfs/
        ├── ocr-flow.log         # 处理日志
        └── titles_guide.md      # 标题生成指南（给 Claude Code 使用）
```

## 更新日志

### 最新更新

**新功能：**
- 添加 `--compress` 选项控制翻译后 PDF 压缩行为
- 添加 `--recovery` 参数支持非交互模式恢复/重试
- 添加 BabelDOC 翻译 QPS 限制配置 (`qps` 参数)
- PDF 类型检测默认改为 `auto` 自动检测

**Bug 修复：**
- 修复翻译后 PDF 中文乱码问题
- 修复 MinerU CDN SSL 下载问题（支持多种下载方式）
- 修复扫描版 PDF 翻译后文字不可见问题（自动传递 `--ocr-workaround` 给 BabelDOC）
- 修复代理环境下下载问题

**改进：**
- 改进错误处理和用户友好提示
- 添加大文件 OCR 警告
- 改进 CLI 输出，添加进度条

### 早期功能

**基础功能：**
- 日志系统 - 10MB 自动轮转，保留最近 3 个备份
- 文件大小对比 - 处理时自动显示压缩效果
- 标题生成指南 - 处理完成后生成 `titles_guide.md`
- Ctrl+C 安全退出 - 按键中断可保存进度

## 开发

### 运行测试

```bash
pytest tests/ -v
pytest tests/test_pipeline.py -v  # Run single test file
pytest tests/test_mineru.py::test_upload -v  # Run single test
```

### 创建测试 PDF

```bash
python create_stress_test_pdf.py
python create_test_assets.py
```

## API Token 获取

- **MinerU API**: 从 [MinerU 官网](https://mineru.net/) 获取
- **OpenAI 兼容 API**: 用于 BabelDOC 翻译（如通义千问、DeepSeek）

## 常见问题

### SSL 下载错误

如果从 MinerU CDN 下载时遇到 SSL 错误：

1. 安装 `pythonnet`: `uv pip install pythonnet`
2. 工具会自动使用 .NET WebClient 作为备选方案
3. 如果仍失败，工具会尝试使用 curl 作为最终备选

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

### 翻译后中文显示乱码

使用 `--compress` 选项：

```bash
ocr-flow process input.pdf -o output/ --translate --compress -v
```

此选项会禁用字体子集化以兼容 Ghostscript 压缩。

## 许可证

MIT
