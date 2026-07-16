# coding-chong/frankensteined-pdf2md: Windows 新机：从 Clone 到 CPU-only Rapid 验证

本页是 Windows x64 新机器的唯一按序安装手册。先完成本页，再看
[运行时与输出契约](runtime-pipeline.md)、[BabelDOC profile](babeldoc-runtime-profiles.md)
和 [复杂 PDF 矩阵](complex-pdf-live-matrix.md)。

所有命令都必须在仓库 checkout 根目录运行。示例刻意使用锁定的 uv
命令，不依赖全局安装的 ocr-flow，也不要求手动激活虚拟环境。

## 1. Clone 和锁定 Python 环境

用 HTTPS clone，避免把 SSH key 配置当成项目依赖：

~~~powershell
git clone https://github.com/coding-chong/frankensteined-pdf2md.git
Set-Location frankensteined-pdf2md
git status --short --branch
git rev-parse --show-toplevel
uv python install 3.13.12
uv sync --locked --extra windows --extra dev
uv lock --check
uv run --locked --extra windows ocr-flow --help
~~~

正常结果是最后一条显示 ocr-flow 的 config、doctor、process 和 runtime
子命令。开发/离线验证使用的 pytest 来自 dev extra；只运行应用时仍保留
windows extra：

~~~powershell
uv sync --locked --extra windows
uv run --locked --extra windows ocr-flow --help
~~~

不要执行旧式安装方式：进入子目录后执行 uv venv、uv pip install -e，或先
全局安装 ocr-flow。它们绕开了 checkout 根目录的 pyproject.toml 和 uv.lock，
不能复现本仓库的依赖图。

## 2. 外部依赖清单

| 项目 | 何时需要 | 获取和版本边界 | 放置/配置位置 | 无密钥验证 | 失败后的安全处理 |
| --- | --- | --- | --- | --- | --- |
| Git for Windows x64 | 所有工作流 | 官方 Git for Windows；验证基线 2.53.0.windows.1 | PATH | git --version | 安装或升级 Git for Windows，重新开终端后重试。 |
| uv | 所有工作流 | 官方 uv 安装页；验证基线 0.10.6。uv.lock 锁定 Python 包，不把 uv 自身伪装成锁定包。 | PATH | uv --version | 安装官方 x64 uv；若新版本不兼容，回退到 0.10.6 并记录问题。 |
| CPython | 所有工作流 | .python-version 固定 3.13.12，由 uv 下载管理。项目元数据仍声明 Python >=3.9。 | uv 管理的位置，不是项目内手工复制的 Python | uv run --locked --extra windows python --version | 运行 uv python install 3.13.12；不要改 uv.lock 绕过解释器问题。 |
| 锁定 Python 包 | 所有工作流 | 仓库内 uv.lock；Windows extra 包含 pythonnet 3.0.5。 | checkout 下 .venv，已被 Git 忽略 | uv lock --check 和 uv sync --locked --extra windows --dry-run | 删除本地 .venv 后重新执行 uv sync --locked；不要手工 uv pip install 覆盖锁。 |
| pythonnet 和 .NET | Windows MinerU ZIP 回退链 | pythonnet 3.0.5 由 windows extra 锁定；已验证 .NET Desktop Runtime 8.0.3。 | Python 环境和 Windows .NET 运行时 | uv run --locked --extra windows python -c "import clr; from System.Net import WebClient; print('pythonnet/.NET ready')" | 仅当该命令失败时安装 Microsoft x64 .NET Desktop Runtime LTS，重开终端后重跑。 |
| Ghostscript | 所有不翻译流程；显式 `--compress` 的翻译流程；完整矩阵 | 从 Artifex Ghostscript 官方下载页获取 Windows x64。当前发现基线 10.03.0；10.07.1 曾通过真实压缩兼容性验证。 | PATH，或 config 的 compress.ghostscript_path | uv run --locked --extra windows ocr-flow doctor | 提供真实 gswin64c.exe 的绝对路径；下载或签名成功不等于兼容，须做后述压缩 smoke。 |
| Umi-OCR Rapid | 扫描 PDF、CPU-only 路径、CPU/Rapid 矩阵 | 官方 GitHub release v2.1.5 的 Umi-OCR_Rapid_v2.1.5.7z.exe；不要下载 Paddle 包来代替 Rapid。 | 用户选定目录，例如 C:\Tools\Umi-OCR_Rapid_v2.1.5；config 的 umiocr.exe_path | verify_umiocr_runtime.py 加 --engine rapid，随后运行本地 layered-PDF smoke | 重新从官方 release 解压到新目录；不要提交 vendor binary；若 options 显示 Paddle model 路径，先关闭错误服务再启动 Rapid。 |
| BabelDOC | 仅翻译 | 项目自动管理 v0.6.3，提交 28f784ca6b437dbba040bfd9c67110373cd0924b | checkout/.ocr-flow-runtime/BabelDOC，已被 Git 忽略 | runtime setup --profile cpu-safe，随后 runtime smoke | 运行 setup 重新创建项目托管目录。不要对自己的 checkout 运行 runtime setup --path，除非接受其破坏性清理。 |
| MinerU token | 每个 process 和 live matrix；即使不翻译也需要 | 用户在 MinerU 账户中创建 token；服务版本不由 Python lock 控制 | 用户配置文件 %USERPROFILE%\.ocr-flow\config.toml 或 process 的 --config 文件 | ocr-flow doctor 只检查已配置，不提交请求 | 检查账户、额度和网络；不要把 token 放进仓库、日志或 issue。 |
| 翻译 provider/key | 仅 --translate 和 live matrix 的两个翻译 case | 用户选择兼容 OpenAI API 的服务；默认配置示例是 DashScope qwen3.5-flash，不是项目锁定依赖 | 用户配置中的 babeldoc 段 | runtime smoke 只检查本地运行时；一次显式翻译才验证远端 key | 更新用户配置或 provider 配额；不要把 key 写入 README、测试或输出。 |
| 网络、防火墙、curl、PowerShell | Git clone、uv/BabelDOC 下载、MinerU 和翻译时需要出站 HTTPS | curl.exe 和 powershell.exe 是常见 Windows 自带工具，不是需要安装的项目依赖 | 系统 PATH | Get-Command curl.exe,powershell.exe | 缺少它们不阻止 requests 主路径；仅失去对应 MinerU ZIP 回退。检查企业防火墙、TLS inspection 和账户网络策略。 |

PySocks 不在表中，也不是项目依赖：代码没有导入它，uv.lock 也没有锁定它。
不要为了本项目额外安装 PySocks。

## 3. 用户配置和 Rapid CPU-only 选择

运行一次向导会在用户目录创建默认配置。doctor 不接受 --config，因此 Rapid
的普通开发/诊断配置应保存在这个默认位置：

~~~powershell
uv run --locked --extra windows ocr-flow config
~~~

向导中选择 Rapid，并填写 Umi-OCR.exe 的绝对路径、MinerU token、翻译 key
和可选 Ghostscript 路径。Rapid 相关段的最终形状应类似下面这样；密钥不要写入
示例文件或 Git：

~~~toml
[umiocr]
engine = "rapid"
url = "http://127.0.0.1:1224"
language = "English"
exe_path = "C:/Tools/Umi-OCR_Rapid_v2.1.5/Umi-OCR.exe"

[compress]
ghostscript_path = "C:/Program Files/gs/gs10.07.1/bin/gswin64c.exe"
quality = "ebook"
~~~

engine 缺失时保留旧配置的 paddle 行为。Rapid 的文档 API 接受 English 和
简体中文；Paddle 的 models/config_en.txt 和 models/config_chinese.txt 不能
当作 Rapid 值。process 的 --lang en 或 --lang zh 会按 engine 映射，doctor
和 OCR 上传前都会读取 GET /api/doc/get_options，拒绝运行中服务与配置不匹配的
情况。

## 4. 不消耗额度的准备检查

先确认 Python/.NET 边界和已跟踪的 fixture：

~~~powershell
uv run --locked --extra windows python -c "import clr; from System.Net import WebClient; print('pythonnet/.NET ready')"
uv run --locked --extra windows --extra dev pytest tests/test_complex_pdf_assets.py tests/test_live_matrix_validation.py -q
uv run --locked --extra windows python scripts/generate_complex_pdf_scan.py --verify
~~~

Rapid 必须同时通过文件指纹和真实本地 document OCR。以下命令没有 MinerU 或
翻译调用；它会在需要时启动本地 Umi-OCR，并产出可人工打开的 layered PDF：

~~~powershell
$umiRoot = "C:\Tools\Umi-OCR_Rapid_v2.1.5"
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path $umiRoot --engine rapid
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py --input test_assets\test_page_scanned.pdf --output output\rapid-local-smoke\test_page_scanned.layered.pdf --umiocr "$umiRoot\Umi-OCR.exe" --engine rapid --lang en
uv run --locked --extra windows ocr-flow doctor --ocr --start-ocr
~~~

人工打开 output\rapid-local-smoke 下的 PDF：页数应等于输入，且可选中/复制 OCR
文字。若 doctor 报 Rapid 期望 English 但服务提供 models/config_en.txt，说明
1224 端口仍是 Paddle 服务；关闭它后重试，不要修改 Rapid 配置去伪装 Paddle。

CPU-only 翻译路径只使用 cpu-safe profile：

~~~powershell
uv run --locked --extra windows ocr-flow runtime setup --profile cpu-safe
uv run --locked --extra windows ocr-flow runtime smoke --profile cpu-safe --input test_assets\test_page_text.pdf
uv run --locked --extra windows ocr-flow runtime status
~~~

不要在 CPU-only 机器执行 windows-directml 或 --all-profiles。隔离 clone 可以
证明没有隐藏配置/源码依赖；只有在物理上没有 GPU 的主机上完成以上 Rapid 与
cpu-safe smoke，才是硬件独立性的最终证明。

若更换 Ghostscript，先以本地一页 fixture 验证输出能打开且页数不变：

~~~powershell
uv run --locked --extra windows python -c "from pathlib import Path; import fitz; from ocr_flow.config import Config; from ocr_flow.steps.compress import compress_pdf; c=Config(); c.compress.ghostscript_path=r'C:\path\to\gswin64c.exe'; p=compress_pdf(Path('test_assets/test_page_text.pdf'), Path('output/ghostscript-smoke'), c); print(f'{p} pages={fitz.open(p).page_count}')"
~~~

### Ghostscript 到底什么时候使用

压缩选择只由“是否翻译”和 `--compress` 决定，文字 PDF 与扫描 PDF 的规则相同：

| 命令选择 | 是否调用 Ghostscript | 原因 |
| --- | --- | --- |
| `--no-translate` | 总是调用 | 非翻译流程默认压缩拆分后的 PDF；是否写 `--compress` 不改变结果。 |
| `--translate`，不写 `--compress` | 不调用 | 默认保留 BabelDOC 的字体子集和中文编码行为。此流程无需 Ghostscript。 |
| `--translate --compress` | 调用 | 用户明确要求压缩双语 PDF；压缩片段保留在 `final/compressed_pdfs/`。 |

因此，只做翻译且不压缩的用户可以不安装 Ghostscript；任何不翻译的正常转换都
必须先让 `doctor` 找到可用的 Ghostscript。完整四案例矩阵同时包含非翻译压缩和
翻译压缩案例，所以矩阵始终要求 Ghostscript。

## 5. 正常处理命令

### 统一部署预检

受支持机器不是“只能跑其中一种工作流”的分级概念。它必须以标准 Windows 用户
完成文字/扫描、翻译/不翻译、Rapid CPU OCR、portable Ghostscript、cpu-safe
BabelDOC，以及第 7 节完整四案例矩阵。管理员权限只能用于可替换的一次性系统
安装；正常安装、预检和运行不得依赖提权。

Ghostscript 无管理员路径是把官方发行版解压到用户可写目录（例如
`%LOCALAPPDATA%\OCR-Flow\Ghostscript\`），然后在配置向导中把
`compress.ghostscript_path` 指向其中真实的 `gswin64c.exe`。不要只记录下载文件、
安装器启动或签名结果；仍须运行第 4 节的一页压缩 smoke。系统安装与 portable
目录二选一即可，`doctor` 的发现顺序不会改变“真实压缩兼容性才是证据”的规则。

在任何付费处理前运行统一、只读、零配额预检：

~~~powershell
uv run --locked --extra windows ocr-flow doctor --deployment
uv run --locked --extra windows ocr-flow doctor --deployment --json output\deployment-report.json
~~~

`PASS` 是本机已观察到的成功，`FAIL` 是必须先修复的硬前置，`WARN` 是发现了可用
组件但仍缺兼容性 smoke，`UNVERIFIED` 是当前机器不能诚实证明的环境条件。只要有
required `FAIL`，命令返回 1 且 verdict 为 `NOT_READY`；存在 `WARN` 或
`UNVERIFIED` 时 verdict 为 `UNVERIFIED`，不能据此声称机器已受支持。JSON 使用
稳定 check ID 和 `<checkout>`、`<user-config>`、`<temp>`、`<output>` 分类路径，
写出前再次扫描密钥、签名 URL 和用户目录；报告只保存在用户指定位置且不会上传。

预检不会启动 Umi-OCR、安装/修改 runtime，也不会调用 MinerU 或翻译 API。它会
明确保留当前主机不能模拟的证据缺口：不同 Windows 内核、物理无 GPU、真实 EDR、
企业 TLS inspection 和真实低内存硬件。最终支持门仍是标准用户下完成 24 个
MinerU parts、两个翻译、全部状态/PDF/Markdown/报告/contact sheets、密钥扫描和
人工视觉复核。

下面命令需要已配置 MinerU token。把 credentialConfig 指向用户拥有的配置；
它不应位于 Git checkout 内。

~~~powershell
$credentialConfig = "$env:USERPROFILE\.ocr-flow\config.toml"
~~~

文字 PDF、不翻译：

~~~powershell
uv run --locked --extra windows ocr-flow process test_assets\test_page_text.pdf -o output\text-smoke --config $credentialConfig --non-interactive --pdf-type text --lang en --no-translate --no-open-output -v
~~~

扫描 PDF、Rapid CPU-only、不翻译：

~~~powershell
uv run --locked --extra windows ocr-flow process test_assets\test_page_scanned.pdf -o output\rapid-scan-smoke --config $credentialConfig --non-interactive --pdf-type scanned --lang en --no-translate --no-open-output -v
~~~

翻译流程额外需要完成 cpu-safe BabelDOC setup 和翻译 provider key：

~~~powershell
uv run --locked --extra windows ocr-flow process test_assets\test_page_text.pdf -o output\translation-smoke --config $credentialConfig --non-interactive --pdf-type text --lang en --translate --no-open-output -v
~~~

每次 Conversion Run 在输出根目录下保留时间戳目录、.state.json、ocr-flow.log、
intermediate、final Markdown、images 和可选 compressed_pdfs。翻译的 dual PDF
保留在 intermediate；使用 --compress 时压缩翻译片段在
final/compressed_pdfs。先人工打开 PDF，再检查 final 中的 Markdown 和图片链接。

处理中断时重用 .state.json，而不是重新提交已经成功的 MinerU 分段：

~~~powershell
uv run --locked --extra windows ocr-flow process <input.pdf> -o <output-dir> --config $credentialConfig --non-interactive --pdf-type <text-or-scanned> --lang en --no-translate --recovery retry --no-open-output -v
~~~

## 6. MinerU ZIP 与 Markdown 图片的不同边界

MinerU 转换结束后，ocr_flow/steps/mineru.py 下载的是结果 ZIP。该受支持链路按
顺序尝试 requests、curl、Windows .NET WebClient、PowerShell，并始终保留系统
CA 验证。标准方法继承系统/环境 proxy；若限定的 OpenXLab CDN 在本机 DNS 下
发生 TLS EOF，最后的 direct-CDN 回退可通过 Google DoH 获得 global IPv4，并用
`curl --resolve` 保持原主机名/SNI/证书验证，只允许 HTTPS 跳转。curl 和
PowerShell 是机会性回退；pythonnet 只为 .NET WebClient 回退提供能力。

之后 ocr_flow/steps/image_download.py 处理 Markdown 图片，这不是 ZIP 下载
回退：它优先从已解压的 MinerU 结果包复制本地图片；只有 Markdown 出现远程 HTTP
图片 URL 时才使用 requests 下载。两条链路不能互相证明成功。需要
`verify=False`、`curl -k` 或 TrustAll 才能成功的结果不能作为支持证据。受限
direct-CDN 回退会仅对该下载绕过 proxy；企业策略禁止直连时应明确失败，不能改
全局 proxy/TLS 设置。本回退必须有真实矩阵证据，mock 命令构造不能证明可用。

## 7. 复杂 PDF 四 case 矩阵

下列文件已经在 Git 中，可从 clone 直接获得：

| 文件 | 用途 |
| --- | --- |
| test_assets/4_gs_prepress_300dpi.pdf | 六页文字层技术论文 fixture。 |
| test_assets/4_gs_prepress_300dpi_scanned_300dpi.pdf | 对应 300 DPI image-only 扫描 fixture。 |
| test_assets/complex_pdf_matrix.json | 哈希、页几何和语义锚点。 |
| scripts/generate_complex_pdf_scan.py | scan fixture 生成/verify。 |
| scripts/run_live_complex_pdf_matrix.py | 真实服务 runner。 |
| tests/live_complex_pdf_matrix.py | 严格 live validator。 |
| tests/test_complex_pdf_assets.py 和 tests/test_live_matrix_validation.py | 不耗额度的资产/可观测性检查。 |

四个 case 是 text_no_translate、scan_no_translate、
text_translate_uncompressed 和 scan_translate_compressed。先重复第 4 节的
离线验证。完整 CPU/Rapid 运行会为一个 cpu-safe profile 消耗 24 个 MinerU
转换和两个翻译请求，因此只能在账户额度和费用获得明确批准后执行：

~~~powershell
uv run --locked --extra windows --extra dev python scripts/run_live_complex_pdf_matrix.py --config $credentialConfig --ghostscript "C:\path\to\gswin64c.exe" --umiocr "$umiRoot\Umi-OCR.exe" --umiocr-engine rapid --profile cpu-safe --output output\live_complex_pdf_matrix
~~~

完成后查看 runner-summary.json、每个 case 的 .state.json、Markdown、PDF、
live-matrix-report.json、live-progress.log 和 visual_review contact sheets。
退出码为零不足以替代人工检查：公式、OCR 文本层、中文字体、翻译版面、压缩页
都必须人眼确认。CPU-only 不使用 --all-profiles；它会额外运行 DirectML 并双倍
消耗服务额度。

## 8. 干净 clone 复查

在另一目录重新 clone 后，重复第 1、4 节中的 uv install、lock、fixture、
Rapid manifest 和 layered-PDF 命令。不要复制 .venv、umiocr_local、
.ocr-flow-runtime、output、API_KEYS.md 或用户 config。它们都被 Git 忽略，
并且复制会掩盖新机缺失的依赖。

复查时可用以下命令确认仓库真正包含矩阵资产：

~~~powershell
git ls-files test_assets/4_gs_prepress_300dpi.pdf test_assets/4_gs_prepress_300dpi_scanned_300dpi.pdf test_assets/complex_pdf_matrix.json scripts/generate_complex_pdf_scan.py scripts/run_live_complex_pdf_matrix.py tests/live_complex_pdf_matrix.py tests/test_complex_pdf_assets.py tests/test_live_matrix_validation.py
~~~

如果上述命令、Rapid local smoke 和 cpu-safe BabelDOC smoke 都成功，新机已具备
不使用 GPU 的离线/本地准备条件。MinerU、翻译和完整四 case 矩阵仍由各自账户、
网络和额度决定，必须把它们作为独立的远端验证门。
