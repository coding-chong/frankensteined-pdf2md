# OCR Flow AI-Friendly CLI and Docs Design

**Date:** 2026-05-10
**Status:** Ready for user review

## Goal

让 AI 和人类首次进入仓库时，不依赖外部项目记忆，也能正确使用 OCR Flow 的 interactive / non-interactive 入口，补全必需参数，理解环境依赖，并预期翻译中间产物的位置。

## Non-Goals

本轮不做以下事情：

- 不修改 `pipeline.py` 的主处理逻辑
- 不改变 OCR / Translate / Split / Compress / MinerU / Format Fix / Image Download 的执行顺序
- 不放宽 non-interactive 模式的参数约束
- 不重构配置系统
- 不引入新的处理能力或新的外部依赖

## Problem Statement

当前仓库已经具备完整功能，但首次使用体验仍然依赖额外上下文，尤其是：

1. AI 或新用户难以仅靠仓库自身信息快速拼出完整的 non-interactive 命令
2. 缺参报错能指出问题，但不能直接把用户带回正确命令
3. `doctor` 更偏向环境检查器，而不是“下一步该做什么”的引导入口
4. 交互模式能完成提问，但对关键选择的后果解释不足
5. 翻译场景下，用户不一定知道双语 PDF 会早于 Markdown 产出

这会导致 AI 需要借助项目外部记忆来补足调用细节，也会让人类用户在首次使用时反复试错。

## Design Principles

### 1. Repository-first discoverability

仓库自身应成为唯一可信入口。用户和 AI 应优先从以下入口得到正确信息：

- `README.md`
- `ocr-flow process --help`
- 缺参或失败时的 CLI 报错
- `ocr-flow doctor`

`CLAUDE.md` 只作为补充，不承担主入口职责。

### 2. Strict commands, easier correction

non-interactive 模式保持严格，不减少必填参数，不做自动猜测。
优化方向是让错误更容易被修正，而不是让校验更宽松。

### 3. Every entry point gives the next executable command

所有关键用户可见入口都应在最短文本内给出下一条可执行命令。

- `README.md`：告诉第一次怎么跑
- `--help`：告诉当前命令怎么补全
- 缺参报错：告诉当前失败怎么立刻修正
- 交互 prompt：告诉当前选择会带来什么结果
- `doctor`：告诉环境未就绪时下一步做什么
- 所有命令模板优先使用长参数名和占位符，降低 AI 与人类误读概率

### 4. Preserve stable pipeline behavior

这轮优化只改入口层、提示层、文档层、诊断层和相关测试，不碰已经稳定的处理主流程。

## File-Level Design

### 1. `README.md`

**Role:** 仓库的唯一主入口。

**Responsibilities:**

- 在前部给出最短成功路径
- 在 README 前部（建议前 80 行内）给出首个完整可复制命令
- 给出完整 non-interactive 命令模板
- 将 Quick Start 和命令模板置于安装/配置细节之前
- 明确 interactive 与 non-interactive 的选择方式
- 给出常见报错与修正命令对照
- 说明 `doctor`、`config`、`recovery` 的典型使用顺序
- 明确翻译场景下双语 PDF 会先出现在 `intermediate/`，Markdown 是后续步骤

**Content structure:**

1. 一句话说明工具目标
2. Quick Start
3. Non-interactive required arguments
4. Copyable command templates
5. Interactive mode
6. Common mistakes and fixes
7. Doctor / config / recovery
8. Output structure and translated intermediate artifact notes

### 2. `ocr_flow/cli.py`

**Role:** 命令入口和所有主要用户可见提示的控制层。

**Responsibilities:**

- 重构 `process` 命令的 help 展示顺序
- 在 `--non-interactive` 相关 help 中直接标出必需项
- 将缺参报错升级为“错误 + 完整修正示例”
- 优化交互模式提问顺序
- 为关键选项提供一行后果说明
- 统一 `doctor` 结果的渲染方式
- 在完成或恢复相关提示中给出明确下一步

**Prompt design constraints:**

- 文案简短，不把 README 级别说明塞进 prompt
- 只在关键分叉点解释后果：
  - `text / scanned / auto`
  - `translate / no-translate`
- 示例命令统一使用占位符风格：
  - `ocr-flow process <input.pdf> -o <output_dir> ...`

### 3. `ocr_flow/self_check.py`

**Role:** 产出结构化诊断语义。

**Responsibilities:**

- 返回依赖状态
- 返回失败原因
- 返回建议下一步动作
- 不承担长篇用户文案展示

**Boundary:**

`self_check.py` 负责“诊断是什么”，`cli.py` 负责“如何把诊断展示成用户可照抄的输出”。

### 4. `tests/test_cli.py`

**Role:** 保护自解释接口不回退。

**Responsibilities:**

- 验证 non-interactive 缺参时的纠偏输出
- 验证 `process --help` 中的关键规则和模板
- 验证 `doctor` 的成功/失败提示具备下一步引导能力
- 验证关键提示不会在后续改动中退化

### 5. `ocr_flow/config.py` (optional)

**Role:** 配置向导的补位优化。

**Only change if needed:**

- 当现有配置向导文案明显妨碍首次使用时，才做局部调整
- 不扩展配置模型
- 不引入复杂配置概念

### 6. `CLAUDE.md` (optional)

**Role:** 仓库内 AI agent 补充说明。

**Constraints:**

- 只保留短小的 canonical invocation patterns
- 明确 README 是主入口
- 不把关键使用知识只放在这里

## User-Facing Text Design

### A. Non-interactive missing argument errors

错误提示不应只指出缺少哪个参数，还应直接给出修正命令。

Example style:

```text
Error: --lang is required in non-interactive mode.

Example:
  ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v
```

```text
Error: --translate or --no-translate is required in non-interactive mode.

Examples:
  ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --translate -v
  ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v
```

### B. `process --help`

help 不只列参数，还要在顶部提供规则块和常用模板。

Required concepts to expose:

- non-interactive requires `--lang`
- non-interactive requires `--translate` or `--no-translate`
- 至少一条 text PDF 示例
- 至少一条 scanned PDF 示例
- 一条 interactive 入口示例

### C. Interactive prompts

交互模式应从“裸提问”变成“简短解释型向导”。

Required behavior:

- `text / scanned / auto` 说明各自适用场景
- `translate / no-translate` 说明会不会先生成双语 PDF
- 若选择 scanned，提示 UMI OCR 依赖及 `doctor` 的下一步命令
- 每个问题最多补一行解释，不扩写成长段文案

### D. `doctor`

`doctor` 输出应遵循“状态 + 下一步命令”的结构。

Required behavior:

- 若检查失败：明确指出下一步可执行命令
- 若检查成功：给出一条最小可运行命令
- 成功示例必须与当前已验证能力匹配，未配置翻译或 OCR 时不得给出对应场景命令
- 对 scanned/text 场景的分支提示保持清晰

## Verification Strategy

### 1. CLI regression tests

至少覆盖以下场景：

1. non-interactive 缺 `--lang`
   - 命令退出
   - 输出包含 `--lang is required`
   - 输出包含完整修正示例

2. non-interactive 缺 `--translate/--no-translate`
   - 命令退出
   - 输出包含对应报错
   - 输出包含两条完整修正示例

3. `process --help`
   - 输出包含 non-interactive required rules
   - 输出包含 text/scanned/invocation templates

4. `doctor` success/failure flows
   - success 至少给一条最小可运行命令
   - failure 至少给一条下一步建议命令

### 2. README execution review

README 中的关键命令应被当作受约束接口维护，至少人工验证以下路径：

- text PDF non-interactive, no translate
- text PDF non-interactive, translate
- scanned PDF non-interactive, no translate
- scanned PDF non-interactive, translate
- interactive entry
- doctor entry
- config entry

### 3. Acceptance criteria for AI-friendly usage

一个没有项目外部记忆、也不依赖 `CLAUDE.md` 的 AI，仅靠仓库内主入口，应该能够：

1. 只读 `README.md` 前部就拼出完整 non-interactive 命令
2. 只看 `ocr-flow process --help` 就知道 non-interactive 必填项
3. 在故意漏掉 `--lang` 或 `--translate/--no-translate` 后，能从报错中直接修正命令
4. 在环境未就绪时，通过 `ocr-flow doctor` 知道下一步
5. 在交互模式中，根据简短说明做出正确选择
6. 在翻译场景中，预期双语 PDF 会先于 Markdown 出现，并知道其位于 `intermediate/`

## Risks and Mitigations

### Risk: 文案改多了但价值不集中

**Mitigation:** 所有用户可见入口只承担一种纠偏职责，避免同一段说明在多个地方无限扩写。

### Risk: 帮助信息和 README 漂移

**Mitigation:** 用测试固定 CLI 输出关键语义；README 结构则在实现计划里列为明确维护项。

### Risk: 优化入口层时误伤主流程

**Mitigation:** 明确不修改 pipeline 主处理逻辑，不改变现有处理顺序。

## Summary

这次优化不是功能重写，而是给 OCR Flow 增加一层仓库内自解释接口。

成功的定义不是“文案更丰富”，而是：

- 用户和 AI 不需要外部项目记忆
- 仓库自身就足以引导正确调用
- 出错时能立刻纠偏
- 环境缺失时知道下一步
- 翻译场景下知道双语 PDF 的出现时机和位置
