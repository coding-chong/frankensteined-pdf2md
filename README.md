# coding-chong/frankensteined-pdf2md: PDF to Markdown Converter

coding-chong/frankensteined-pdf2md 将技术 PDF 转为可恢复、可审计的 Markdown，面向芯片手册、数据
手册和同类技术文档。它可以处理带文字层的 PDF，也可以先为扫描件生成 OCR
文字层；可选地保留 BabelDOC 的双语 PDF，再通过 MinerU 生成带本地图片的
Markdown。

这是一个 Windows x64 工具。每次 `process` 都会调用 MinerU，需要用户自己的
token 和账户额度；使用 `--translate` 还需要兼容 OpenAI API 的翻译服务 key。
本 README 按一次完整转换的顺序说明：准备环境、配置、预检、处理、检查产物和
恢复。所有命令都应在本仓库 checkout 根目录执行。

## 处理前先判断

| 你的 PDF 或目标 | 需要的组件 | 从哪里开始 |
| --- | --- | --- |
| 带可选中文字的文字 PDF，不翻译 | MinerU、Ghostscript | 从步骤 1 顺序完成到步骤 4 |
| 扫描件或图片 PDF，不翻译 | MinerU、Ghostscript、[hiroi-sora/Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) 的已选引擎 | 从步骤 1 顺序完成到步骤 4 |
| 需要翻译并保留双语 PDF | [opendatalab/MinerU](https://github.com/opendatalab/MinerU)、[funstory-ai/BabelDOC](https://github.com/funstory-ai/BabelDOC) v0.6.3、兼容 OpenAI API 的翻译服务 key（默认示例：DeepSeek `deepseek-chat`） | 从步骤 1 顺序完成到步骤 4 |

扫描件是否需要 OCR，不以文件名判断：无法在 PDF 阅读器中选中正文文字时，按
扫描件处理。`--lang en` 和 `--lang zh` 是源文档语言；非交互命令必须同时指定
`--lang` 与 `--translate` 或 `--no-translate`。

## 1. 准备 checkout

先安装 Git for Windows 和 [uv](https://docs.astral.sh/uv/)，然后在 PowerShell
中执行：

~~~powershell
git clone https://github.com/coding-chong/frankensteined-pdf2md.git
Set-Location frankensteined-pdf2md
uv python install 3.13.12
uv sync --locked --extra windows
uv lock --check
uv run --locked --extra windows ocr-flow --help
~~~

最后一条应显示 `config`、`doctor`、`process` 和 `runtime` 子命令。不要进入
`ocr_flow` 子目录安装，也不要全局安装 `ocr-flow` 或手动创建项目虚拟环境；这些
方式会绕开仓库锁定的依赖。

Windows 新机的完整安装顺序、Paddle OCR V6 插件环境与模型准备、Rapid 下载、版本
边界和本地验证在
[Windows 新机与 OCR V6 安装](docs/fresh-clone-setup.md)。

## 2. 安装外部组件，然后使用 ocr-flow 交互式配置

下表的仓库名是外部组件的权威来源；本仓库只配置和验证它们，不分发或维护其
二进制文件。

| 组件 | 上游来源 | 在本流程中的作用 |
| --- | --- | --- |
| Git for Windows | [git-for-windows/git](https://github.com/git-for-windows/git) | clone 和版本控制。 |
| uv | [astral-sh/uv](https://github.com/astral-sh/uv) | 安装锁定的 Python 与项目依赖。 |
| CPython | [python/cpython](https://github.com/python/cpython) | 由 uv 管理；本项目固定 3.13.12。 |
| Umi-OCR | [hiroi-sora/Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) 的 [v2.1.5 Release](https://github.com/hiroi-sora/Umi-OCR/releases/tag/v2.1.5)；Paddle plugin 使用 [chapterv/umi-paddle-neoengine](https://github.com/chapterv/umi-paddle-neoengine) 1.4.2 | 扫描 PDF 的本地 OCR。默认 Paddle OCR V6 profile 使用 plugin-local Python 3.12.10、PaddlePaddle 3.2.1、PaddleOCR 3.7.0 和 ONNX Runtime 1.26.0 的 CPU backend；Rapid 是独立可选引擎。 |
| Ghostscript | [ArtifexSoftware/ghostpdl](https://github.com/ArtifexSoftware/ghostpdl)；[官方 Windows 下载页](https://ghostscript.com/releases/gsdnld.html) | 所有不翻译流程，以及带 `--compress` 的翻译流程。 |
| BabelDOC | [funstory-ai/BabelDOC](https://github.com/funstory-ai/BabelDOC) | 翻译时由本仓库管理固定的 v0.6.3 / `28f784ca6b437dbba040bfd9c67110373cd0924b` runtime。 |
| MinerU | [opendatalab/MinerU](https://github.com/opendatalab/MinerU)；[官方平台](https://mineru.net/) | 每次 `process` 的 Markdown 结构化转换与 token 来源。 |

翻译 provider 不是本项目指定或分发的依赖。DeepSeek `deepseek-chat` 是配置向导
的默认示例，用户可以自行配置任何兼容 OpenAI API 的服务和 key；不要把 key 写进
仓库或命令示例。运行 `ocr-flow config` 是首次使用时唯一需要跟随的交互式配置流程。
它会在用户目录创建 `%USERPROFILE%\.ocr-flow\config.toml`；token 和 key 只应保存在
这个用户配置中，绝不能提交到仓库。

~~~powershell
uv run --locked --extra windows ocr-flow config
~~~

### 向导中的每一项怎么填

| 向导提示 | 普通用户的动作 |
| --- | --- |
| `MinerU API Token` | 所有处理都需要。粘贴自己的 MinerU token。 |
| `OpenAI API Key (for BabelDOC translation)` | 只在翻译时需要。使用 DeepSeek 时粘贴 DeepSeek key；暂不翻译可留空。 |
| `OpenAI model` | 使用默认 DeepSeek 时直接按 Enter，保留 `deepseek-chat`；其他兼容服务时输入其模型名。 |
| `OpenAI Base URL` | 使用默认 DeepSeek 时直接按 Enter，保留 `https://api.deepseek.com`；其他兼容服务时输入其 endpoint。 |
| `BabelDOC Git checkout (leave empty for managed runtime)` | 普通用户直接按 Enter。不要 clone BabelDOC，也不要填写路径。 |
| `BabelDOC primary font family` | 直接按 Enter 保持 `auto`，除非你明确需要 serif、sans-serif 或 script。 |
| `Ghostscript path` | 已安装且在 PATH 中时直接按 Enter；否则填写真实的 `gswin64c.exe` 路径。 |
| `UMI OCR engine` | 默认选 `paddle`，它以 ONNX CPU 运行 OCR V6；只有明确需要独立 Rapid runtime 时才选 `rapid`。GPU 是 Paddle 的显式可选加速验证，不是默认。 |
| `UMI OCR exe path` | 填写已通过下述完整校验的 `Umi-OCR.exe` 绝对路径。仅路径存在或能返回 Paddle language options，不能证明它已安装 OCR V6 plugin。 |

此表与向导的实际提问顺序一致。配置完成后再决定是否安装翻译 runtime、验证扫描 OCR
或直接处理 PDF。

### 自动化或无交互配置

`ocr-flow config` 没有 `--non-interactive` 参数。脚本、CI 或部署工具应直接生成
TOML 配置文件，而不是伪造向导输入。仓库提供了不含凭据的
[`config.example.toml`](config.example.toml)：

~~~powershell
$credentialDir = "$env:USERPROFILE\.ocr-flow"
$credentialConfig = "$credentialDir\config.toml"
New-Item -ItemType Directory -Force $credentialDir
Copy-Item .\config.example.toml $credentialConfig
~~~

让你的密钥管理或部署工具把 MinerU token 写入 `[mineru].api_token`；翻译时再写入
`[babeldoc].openai_api_key`。保留 `openai_model = "deepseek-chat"`、
`openai_base_url = "https://api.deepseek.com"` 和 `babeldoc.path = ""`，除非你的
自动化明确要使用其他兼容 provider 或已经通过 `runtime setup --path` 准备好的外部
BabelDOC checkout。模板注释列出了 Paddle 与 Rapid 必须配对的 language 值。

正常情况下，把文件写到上述默认路径；`ocr-flow doctor` 只读取它，不能接受
`--config`。批处理若使用另一份生成的配置文件，可在第 5 节的命令中传入
`--config $credentialConfig`。

翻译首次使用前，安装项目托管的 BabelDOC runtime：

~~~powershell
uv run --locked --extra windows ocr-flow runtime setup
uv run --locked --extra windows ocr-flow runtime status
~~~

不带 `--path` 的 `runtime setup` 会在 checkout 下创建并安装
`.ocr-flow-runtime/BabelDOC`。`cpu-safe` 是默认 CPU-only 翻译 profile。只有已拥有
BabelDOC Git checkout 的高级用户才填写路径，并在理解该 checkout 会被清理和固定到
测试版本后运行 `ocr-flow runtime setup --path <checkout>`；它不能替代普通用户的
托管 runtime。

`windows-directml` 是独立的、显式选择的 BabelDOC 翻译 profile，不能从 Umi-OCR 的
Paddle/Rapid 选择推断出来。

## 3. 在付费处理前预检

先检查已配置的常规依赖：

~~~powershell
uv run --locked --extra windows ocr-flow doctor
~~~

处理扫描件时，先按硬件验证选定的 Umi-OCR 引擎。两条路径都需要 manifest 校验和
可打开、页数匹配、可提取文字的 layered PDF；不能用一个引擎的成功替代另一个。

### Paddle：NeoEngine ONNX CPU baseline

按 [Windows 新机与 OCR V6 安装](docs/fresh-clone-setup.md#21-安装-paddle-neoengine-ocr-v6默认-cpu-路径)
取得官方 `Umi-OCR_Paddle_v2.1.5.7z.exe`，并在
`UmiOCR-data/plugins/win_x64_PaddleOCR_Py` 安装
[umi-paddle-neoengine](https://github.com/chapterv/umi-paddle-neoengine) 1.4.2。该指南包含
固定源码检出、UTF-8 launcher、插件 `.venv`、依赖、模型、安装状态、回滚和故障重跑命令。
固定 commit 为 `6a87fc4145a13b09104836cb22cf05125b143041`，plugin-local 环境必须是
Python 3.12.10、PaddlePaddle 3.2.1、PaddleOCR 3.7.0 和 ONNX Runtime 1.26.0，
并在插件自己的 PaddleX cache 中保存 `PP-OCRv6_medium_det_onnx`、
`PP-OCRv6_medium_rec_onnx` 与 `PP-LCNet_x1_0_doc_ori_onnx`。配置向导中
保持或选择 `engine = "paddle"`，然后验证静态文件、全部依赖、ONNX
`CPUExecutionProvider` 和三个 OCR V6/方向模型：

~~~powershell
$umiRoot = "C:\Tools\Umi-OCR_Paddle_v2.1.5"
& "$umiRoot\UmiOCR-data\plugins\win_x64_PaddleOCR_Py\.venv\Scripts\python.exe" "$umiRoot\UmiOCR-data\plugins\win_x64_PaddleOCR_Py\install_status.py" check-env --env cpu --backend onnxruntime --models ready
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path $umiRoot --engine paddle --check-environment --provider-mode cpu
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py --input test_assets\test_page_scanned.pdf --output output\paddle-local-smoke\test_page_scanned.layered.pdf --umiocr "$umiRoot\Umi-OCR.exe" --engine paddle --lang en --provider-mode cpu --report output\paddle-local-smoke\report.json
~~~

第一条命令生成 Umi 主程序实际读取的 `install_status.json`。后续 verifier 仍会
独立检查依赖版本、provider 与三个非空模型文件，所以状态值不能替代真实安装。
`run.cmd` 必须保持 v1.4.2 的 UTF-8 环境和便携布局探测；OCR 管道遇到模型下载器的
非 JSON stdout 诊断时会记录并继续等待第一条合法 JSON，而不是把 404 诊断报告为
Umi 904。真实 layered-PDF smoke 才能证明该恢复路径可用。

GPU 仅是显式可选加速：使用独立 `.venv_gpu` 并把两条命令的 provider 改为
`--provider-mode gpu`。只有校验器看到 `CUDAExecutionProvider`、GPU device，且真实
Umi 引擎日志明确报告 `backend=gpu(onnx-cuda) device=gpu` 且无 CPU fallback，才可
记为 GPU 成功；否则继续使用上述 CPU 默认路径。

### CPU-only：Rapid

从同一 [hiroi-sora/Umi-OCR v2.1.5 Release](https://github.com/hiroi-sora/Umi-OCR/releases/tag/v2.1.5)
取得 `Umi-OCR_Rapid_v2.1.5.7z.exe`，在配置向导中选择 `engine = "rapid"`，然后验证：

~~~powershell
$umiRoot = "C:\Tools\Umi-OCR_Rapid_v2.1.5"
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path $umiRoot --engine rapid
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py --input test_assets\test_page_scanned.pdf --output output\rapid-local-smoke\test_page_scanned.layered.pdf --umiocr "$umiRoot\Umi-OCR.exe" --engine rapid --lang en
~~~

通过已选引擎验证后，启动并检查本地 Umi-OCR：

~~~powershell
uv run --locked --extra windows ocr-flow doctor --ocr --start-ocr
~~~

需要确认整台机器是否具备完整部署条件时，运行统一预检：

~~~powershell
uv run --locked --extra windows ocr-flow doctor --deployment
uv run --locked --extra windows ocr-flow doctor --deployment --json output\deployment-report.json
~~~

部署预检不启动或安装 runtime，也不调用 MinerU 或翻译 API。`READY` 表示已通过
本机可观察的检查；`NOT_READY` 先修复失败项；`UNVERIFIED` 表示仍有环境证据未在
本机验证。它不是一次转换的替代品。

## 4. 日常处理

完成步骤 1 到 3 后，日常处理只需要给出输入和输出路径：

~~~powershell
uv run --locked --extra windows ocr-flow process "<input.pdf>" -o "<output-dir>" -v
~~~

没有配置文件时，这个命令会先启动第 2 节的配置向导；建议显式运行 `ocr-flow config`
完成配置后再处理。处理时会询问 PDF 类型、源文档语言和是否翻译。扫描件先完成步骤 3
中与你硬件相符的 Paddle 或 Rapid 检查；选择翻译前先完成项目托管 BabelDOC runtime
安装。选择不翻译时，Ghostscript 必须可用。

处理完成后检查 PDF、Markdown 和图片，再按第 7 节用同一输出目录恢复中断任务。

## 5. 自动化和批处理（可选）

以下非交互命令适用于脚本、CI 或已明确知道每个输入类型的批量处理。它们不替代第 4
节的日常交互路径。将输入 PDF 和输出目录换成自己的路径；使用
`--non-interactive` 时，必须提供 PDF 类型、语言和翻译选择。

~~~powershell
$credentialConfig = "$env:USERPROFILE\.ocr-flow\config.toml"
~~~

### 文字 PDF，不翻译

~~~powershell
uv run --locked --extra windows ocr-flow process "<input.pdf>" -o "<output-dir>" --config $credentialConfig --non-interactive --pdf-type text --lang en --no-translate --no-open-output -v
~~~

这个流程会压缩拆分后的 PDF，因此 Ghostscript 是必需项。

### 扫描 PDF，不翻译

先完成步骤 3 中与硬件相符的 Paddle 或 Rapid 检查，然后执行：

~~~powershell
uv run --locked --extra windows ocr-flow process "<input.pdf>" -o "<output-dir>" --config $credentialConfig --non-interactive --pdf-type scanned --lang en --no-translate --no-open-output -v
~~~

`--lang en` 可以替换成 `--lang zh`。本仓库会将它映射为配置的 OCR 引擎所需
的语言值，并在上传前拒绝配置为 Rapid、实际却运行 Paddle 的服务。

### 翻译 PDF

确认步骤 2 已完成 cpu-safe runtime 和翻译 key 配置后执行：

~~~powershell
uv run --locked --extra windows ocr-flow process "<input.pdf>" -o "<output-dir>" --config $credentialConfig --non-interactive --pdf-type text --lang en --translate --no-open-output -v
~~~

把 `--pdf-type text` 改为 `--pdf-type scanned` 可翻译扫描件。翻译默认不调用
Ghostscript，以保留 BabelDOC 的字体和中文编码；只有明确加入 `--compress` 时才会
压缩翻译片段，并因此需要 Ghostscript：

~~~powershell
uv run --locked --extra windows ocr-flow process "<input.pdf>" -o "<output-dir>" --config $credentialConfig --non-interactive --pdf-type scanned --lang en --translate --compress --no-open-output -v
~~~

## 6. 检查结果

一次 Conversion Run 会在输出根目录创建带时间戳的目录：

~~~text
<output-root>/<timestamp>/<source-stem>/
  .state.json
  ocr-flow.log
  intermediate/
  final/
    part_001.md
    images/
    compressed_pdfs/  # 仅翻译且使用 --compress
  titles_guide.md
~~~

先在 PDF 阅读器中检查 `intermediate/` 中保留的 layered PDF 或双语 PDF，再检查
`final/` 的 Markdown、图片链接和页面顺序。不要只看命令退出码：公式、OCR
文字、中文字符和版面需要人工确认。

## 7. 从中断处恢复

保留同一个输出目录中的 `.state.json`，避免重新提交已成功的 MinerU 分段。将原有
转换命令加上 `--recovery retry`：

~~~powershell
uv run --locked --extra windows ocr-flow process "<input.pdf>" -o "<output-dir>" --config $credentialConfig --non-interactive --pdf-type <text-or-scanned> --lang en --no-translate --recovery retry --no-open-output -v
~~~

恢复策略 `continue`、`retry`、`continue_retry` 和 `restart` 的行为，以及状态文件
和中间产物的边界见 [运行时与输出契约](docs/runtime-pipeline.md)。Windows 上的深层
矩阵输出会先在同盘短路径暂存区解压 MinerU ZIP；合并前会拒绝符号链接和文件/目录
类型冲突，并优先持久化 Markdown，避免长路径或后续 I/O 错误丢失已完成分段。

## 8. 验证完整工具链

日常转换走步骤 1 到 6。若要声明 CPU-only 机器或一次发布支持完整默认 CPU/Paddle
工作流，还必须运行真实的六页复杂 PDF 矩阵：文字/扫描件各一条不翻译和翻译路径，
共四个 case。Rapid 是独立可选引擎；声明 Rapid 支持时必须用其 manifest、local smoke
和显式 `--umiocr-engine rapid` 另行运行矩阵。每个 profile 会消耗 24 个 MinerU 转换和
两个翻译请求，必须先获得账户额度和费用批准。

离线检查不消耗额度：

~~~powershell
uv run --locked --extra windows --extra dev pytest tests/test_complex_pdf_assets.py tests/test_live_matrix_validation.py -q
uv run --locked --extra windows python scripts/generate_complex_pdf_scan.py --verify
~~~

真实矩阵的准备、命令、保留证据和人工验收在
[复杂 PDF 真实服务矩阵](docs/complex-pdf-live-matrix.md)。通过 exit code 后仍必须
查看状态文件、Markdown、PDF、报告和 contact sheets。

## 深入资料

| 需要了解什么 | 文档 |
| --- | --- |
| Windows 安装、Paddle OCR V6、版本、组件获取与 Rapid 验证 | [fresh-clone-setup.md](docs/fresh-clone-setup.md) |
| 管线阶段、输出、配置与恢复规则 | [runtime-pipeline.md](docs/runtime-pipeline.md) |
| BabelDOC runtime 与 DirectML profile | [babeldoc-runtime-profiles.md](docs/babeldoc-runtime-profiles.md) |
| 六页复杂 PDF 的真实服务矩阵 | [complex-pdf-live-matrix.md](docs/complex-pdf-live-matrix.md) |
| 维护仓库、测试和外部服务边界 | [ai-maintenance-guide.md](docs/ai-maintenance-guide.md) |
