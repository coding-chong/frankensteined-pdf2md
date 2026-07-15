# OCR Flow

OCR Flow 将技术 PDF 转为可恢复、可审计的 Markdown。它支持文字 PDF、扫描 PDF
的 Umi-OCR 分层文本、可选 BabelDOC 翻译、Ghostscript 压缩和 MinerU 结构化
转换。

## 先读这里

新 Windows 电脑或新 clone 必须先完成
[Windows 新机：从 Clone 到 CPU-only Rapid 验证](docs/fresh-clone-setup.md)。
该文档是安装顺序、版本、外部依赖、CPU-only Rapid、离线 fixture 和完整矩阵的
唯一权威来源。

不要从 ocr_flow 子目录安装，不要全局安装 ocr-flow，也不要把本地 .venv、
umiocr_local、.ocr-flow-runtime、output 或凭据复制进新 clone。所有命令从本
checkout 根目录通过锁定的 uv 运行。

## 文档导航

| 目标 | 先读 |
| --- | --- |
| 在新电脑安装、配置、CPU-only Rapid 验证 | [fresh-clone-setup.md](docs/fresh-clone-setup.md) |
| 理解处理阶段、输出和恢复 | [runtime-pipeline.md](docs/runtime-pipeline.md) |
| 管理固定 BabelDOC v0.6.3、CPU-safe 和 DirectML profile | [babeldoc-runtime-profiles.md](docs/babeldoc-runtime-profiles.md) |
| 执行或审阅六页复杂 PDF 的真实服务矩阵 | [complex-pdf-live-matrix.md](docs/complex-pdf-live-matrix.md) |
| 维护仓库、测试和外部服务边界 | [ai-maintenance-guide.md](docs/ai-maintenance-guide.md) |

## 已建立环境后的最短路径

这些命令假定已按新机手册创建用户配置并配置 MinerU token。扫描路径还要求
Rapid 已通过本地 layered-PDF 验证。

文字 PDF，不翻译：

~~~powershell
uv run --locked --extra windows ocr-flow process <input.pdf> -o <output-dir> --config "$env:USERPROFILE\.ocr-flow\config.toml" --non-interactive --pdf-type text --lang en --no-translate --no-open-output -v
~~~

扫描 PDF，Rapid CPU-only，不翻译：

~~~powershell
uv run --locked --extra windows ocr-flow doctor --ocr --start-ocr
uv run --locked --extra windows ocr-flow process <input.pdf> -o <output-dir> --config "$env:USERPROFILE\.ocr-flow\config.toml" --non-interactive --pdf-type scanned --lang en --no-translate --no-open-output -v
~~~

翻译 PDF：

~~~powershell
uv run --locked --extra windows ocr-flow runtime setup --profile cpu-safe
uv run --locked --extra windows ocr-flow process <input.pdf> -o <output-dir> --config "$env:USERPROFILE\.ocr-flow\config.toml" --non-interactive --pdf-type text --lang en --translate --no-open-output -v
~~~

非交互模式必须同时给出 --lang 和 --translate 或 --no-translate。翻译路径还需要
用户自己的兼容 OpenAI provider key；任何 process 都会调用 MinerU，因此即使
不翻译也需要 MinerU token 和额度。

## CPU-only Rapid 约定

Umi-OCR 有 Paddle 和 Rapid 两个明确引擎。旧配置不含 engine 时保持 Paddle；
CPU-only 新机应选择 Rapid v2.1.5：

~~~toml
[umiocr]
engine = "rapid"
language = "English"
exe_path = "C:/Tools/Umi-OCR_Rapid_v2.1.5/Umi-OCR.exe"
~~~

--lang en 和 --lang zh 会分别映射为 Rapid 的 English 和 简体中文。OCR Flow
会在上传前读取 Umi-OCR 的 document options；如果端口上运行的是 Paddle 而配置
要求 Rapid，它会明确失败，而不是把 Paddle 路径当成 Rapid 支持。

CPU-only 只使用 BabelDOC 的 cpu-safe profile。不要使用 windows-directml 或
--all-profiles；后者会运行 DirectML 并让 API 消耗翻倍。

## 外部依赖边界

- Python 包由 uv.lock 锁定；Windows extra 锁定 pythonnet 3.0.5。
- Ghostscript、Umi-OCR Rapid、BabelDOC runtime、MinerU 和翻译服务各自有不同
  的获取与验证路径，完整表见新机手册。
- pythonnet 只支持 Windows .NET WebClient 的 MinerU ZIP 回退；它不是 OCR
  引擎。curl.exe 和 PowerShell 也是机会性回退，不是额外安装前置。
- MinerU 结果 ZIP 下载与 Markdown 图片本地化是两条路径：前者使用无环境代理
  的 requests、curl、.NET、PowerShell 回退；后者先复制 ZIP 中本地图片，只在
  Markdown 有远程 HTTP 图片时使用 requests。

## 输出、检查和恢复

一个 Conversion Run 的输出位于：

~~~text
<output-root>/<timestamp>/<source-stem>/
  .state.json
  ocr-flow.log
  intermediate/
  final/
    part_001.md ...
    images/
    compressed_pdfs/
  titles_guide.md
~~~

扫描流程的 layered PDF 位于 intermediate；翻译的 dual PDF 也保留在
intermediate。使用 --compress 时，压缩翻译片段位于 final/compressed_pdfs。
先用 PDF 阅读器做人眼检查，再使用 final Markdown。

Ghostscript 规则：不翻译的流程总会压缩，因此必须安装；翻译流程默认不调用
Ghostscript，只有显式加入 `--compress` 才需要它。文字/扫描 PDF 遵循同一规则。
完整决策表和兼容性 smoke 见 [新机安装手册](docs/fresh-clone-setup.md#ghostscript-到底什么时候使用)。

发生中断时不要重新提交已成功的 MinerU 片段：

~~~powershell
uv run --locked --extra windows ocr-flow process <input.pdf> -o <output-dir> --config "$env:USERPROFILE\.ocr-flow\config.toml" --non-interactive --pdf-type <text-or-scanned> --lang en --no-translate --recovery retry --no-open-output -v
~~~

## 复杂 PDF 验证

仓库跟踪六页 source/scan fixture、manifest、生成器、runner 和离线 validator。
先执行不耗额度检查：

~~~powershell
uv run --locked --extra windows python scripts/generate_complex_pdf_scan.py --verify
uv run --locked --extra windows --extra dev pytest tests/test_complex_pdf_assets.py tests/test_live_matrix_validation.py -q
~~~

真实 CPU/Rapid 矩阵包含四个 case：text_no_translate、scan_no_translate、
text_translate_uncompressed、scan_translate_compressed。一个 cpu-safe profile
消耗 24 个 MinerU 转换和两个翻译请求，必须先获得账户额度和费用的明确批准。
通过 exit code 后仍要查看保留的 PDF、Markdown、状态文件、报告和 contact sheets。

完整命令、可观测输出和人工验收要求在
[complex-pdf-live-matrix.md](docs/complex-pdf-live-matrix.md)。
