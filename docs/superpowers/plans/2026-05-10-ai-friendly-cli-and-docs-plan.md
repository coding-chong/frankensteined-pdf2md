# AI-Friendly CLI and Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 OCR Flow 仅靠仓库内的 README、CLI help、缺参报错和 doctor 输出，就能让 AI 与人类首次进入仓库时写对命令、修正错误并理解翻译中间产物的位置。

**Architecture:** 这次实现只改入口层和提示层，不碰 pipeline 主处理逻辑。`ocr_flow/cli.py` 负责命令模板、help、报错、interactive prompt 和 doctor 渲染；`ocr_flow/self_check.py` 负责返回结构化诊断与下一步建议；`README.md` 负责首屏可发现性；`tests/test_cli.py` 负责保护这些外部接口不回退。

**Tech Stack:** Click, Rich, pytest, Python stdlib

---

## 文件修改清单

| 文件 | 改动类型 | 职责 |
|------|----------|------|
| `ocr_flow/cli.py` | 修改 | 统一命令模板、增强 `process --help`、将 non-interactive 缺参改成带示例的 `UsageError`、改进 interactive prompt、渲染 doctor 下一步命令 |
| `ocr_flow/self_check.py` | 修改 | 为检查结果增加 `next_step` 字段，让 doctor 能基于结构化结果输出下一步命令 |
| `tests/test_cli.py` | 修改 | 锁定 help、缺参报错、interactive prompt 和 doctor 输出的外部行为 |
| `README.md` | 修改 | 把 Quick Start、完整命令模板、常见修正和翻译中间产物说明前置 |

**本计划明确不修改：**
- `ocr_flow/pipeline.py`
- `ocr_flow/config.py`
- `CLAUDE.md`

这些文件不在本轮主实现范围内，因为当前 spec 的验收标准可以通过 README、CLI、doctor 和测试达成。

---

### Task 1: Tighten non-interactive help and missing-argument errors

**Files:**
- Modify: `tests/test_cli.py:315-382`
- Modify: `ocr_flow/cli.py:14-15`
- Modify: `ocr_flow/cli.py:233-245`
- Modify: `ocr_flow/cli.py:359-365`

- [ ] **Step 1: Write the failing tests for `process --help` and non-interactive missing arguments**

Replace the existing `test_process_help`, `test_process_requires_lang_in_non_interactive`, and `test_process_requires_translate_flag` tests in `tests/test_cli.py` with:

```python
def test_process_help(self, runner):
    """Test process command help."""
    result = runner.invoke(cli, ['process', '--help'])

    assert result.exit_code == 0
    assert 'Non-interactive mode requires:' in result.output
    assert '--lang' in result.output
    assert '--translate or --no-translate' in result.output
    assert 'ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --translate -v' in result.output
    assert 'ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type scanned --lang en --no-translate -v' in result.output
    assert 'ocr-flow process <input.pdf> -o <output_dir> -v' in result.output


def test_process_requires_lang_in_non_interactive(self, runner, test_pdf, mock_config):
    """Test that --lang is required in non-interactive mode."""
    result = runner.invoke(cli, [
        'process', str(test_pdf),
        '--non-interactive',
        '--pdf-type', 'text',
    ])

    assert result.exit_code == 2
    assert 'Error: --lang is required in non-interactive mode.' in result.output
    assert 'Example:' in result.output
    assert 'ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v' in result.output


def test_process_requires_translate_flag(self, runner, test_pdf, mock_config):
    """Test that translate flag is required in non-interactive mode."""
    result = runner.invoke(cli, [
        'process', str(test_pdf),
        '--non-interactive',
        '--pdf-type', 'text',
        '--lang', 'en',
    ])

    assert result.exit_code == 2
    assert 'Error: --translate or --no-translate is required in non-interactive mode.' in result.output
    assert 'Examples:' in result.output
    assert 'ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --translate -v' in result.output
    assert 'ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v' in result.output
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli.py -k "test_process_help or test_process_requires_lang_in_non_interactive or test_process_requires_translate_flag" -v
```

Expected: FAIL because `process --help` does not yet expose the required rule block, and the missing-argument paths still return plain `click.echo(...)` output instead of `UsageError` plus example commands.

- [ ] **Step 3: Add shared command templates and usage helpers in `ocr_flow/cli.py`**

Insert this block immediately below `console = Console()` in `ocr_flow/cli.py`:

```python
console = Console()

INTERACTIVE_COMMAND = "ocr-flow process <input.pdf> -o <output_dir> -v"
TEXT_NO_TRANSLATE_COMMAND = (
    "ocr-flow process <input.pdf> -o <output_dir> "
    "--non-interactive --pdf-type text --lang en --no-translate -v"
)
TEXT_TRANSLATE_COMMAND = (
    "ocr-flow process <input.pdf> -o <output_dir> "
    "--non-interactive --pdf-type text --lang en --translate -v"
)
SCANNED_NO_TRANSLATE_COMMAND = (
    "ocr-flow process <input.pdf> -o <output_dir> "
    "--non-interactive --pdf-type scanned --lang en --no-translate -v"
)
SCANNED_TRANSLATE_COMMAND = (
    "ocr-flow process <input.pdf> -o <output_dir> "
    "--non-interactive --pdf-type scanned --lang en --translate -v"
)


def format_command_examples(commands: list[str]) -> str:
    """Format one or more copyable command examples."""
    label = "Example:" if len(commands) == 1 else "Examples:"
    return f"{label}\n" + "\n".join(f"  {command}" for command in commands)


def raise_usage_with_examples(message: str, commands: list[str]) -> None:
    """Raise a Click usage error with copyable command examples."""
    raise click.UsageError(f"{message}\n\n{format_command_examples(commands)}")
```

- [ ] **Step 4: Update the `process` help text and option help in `ocr_flow/cli.py`**

Replace the decorator/help block and command docstring at `ocr_flow/cli.py:233-249` with:

```python
@cli.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), help='Output directory')
@click.option('--config', type=click.Path(), help='Config file path')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.option(
    '--non-interactive',
    is_flag=True,
    help='Non-interactive mode. Requires --lang and either --translate or --no-translate.'
)
@click.option(
    '--pdf-type',
    type=click.Choice(['text', 'scanned', 'auto']),
    default='auto',
    help='PDF type: text, scanned, or auto-detect (default: auto)'
)
@click.option('--lang', type=click.Choice(['en', 'zh']), help='Document language. Required in non-interactive mode.')
@click.option(
    '--translate/--no-translate',
    default=None,
    help='Translation mode. Required in non-interactive mode: choose --translate or --no-translate.'
)
@click.option('--compress', is_flag=True, help='Compress translated PDFs (disables font subsetting to preserve CJK encoding)')
@click.option('--recovery', type=click.Choice(['continue', 'retry', 'continue_retry', 'restart']), default=None, help='Recovery mode for non-interactive mode: continue, retry, continue_retry, restart')
def process(input_path: str, output: str, config: str, verbose: bool,
            non_interactive: bool, pdf_type: str, lang: str, translate: bool, compress: bool, recovery: str):
    """Process PDF file(s) to Markdown.

    INPUT_PATH: PDF file or directory containing PDF files

    Non-interactive mode requires:
      --lang
      --translate or --no-translate

    Common examples:
      ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --translate -v
      ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type scanned --lang en --no-translate -v
      ocr-flow process <input.pdf> -o <output_dir> -v
    """
```

- [ ] **Step 5: Replace the non-interactive validation block with `UsageError` plus examples**

Replace `ocr_flow/cli.py:359-365` with:

```python
    # Non-interactive mode: use provided options
    if not lang and not ask_each_lang:
        raise_usage_with_examples(
            "--lang is required in non-interactive mode.",
            [TEXT_NO_TRANSLATE_COMMAND],
        )
    if translate is None and not ask_each_translate:
        raise_usage_with_examples(
            "--translate or --no-translate is required in non-interactive mode.",
            [TEXT_TRANSLATE_COMMAND, TEXT_NO_TRANSLATE_COMMAND],
        )
```

- [ ] **Step 6: Run the targeted tests to verify they pass**

Run:

```bash
uv run pytest tests/test_cli.py -k "test_process_help or test_process_requires_lang_in_non_interactive or test_process_requires_translate_flag" -v
```

Expected: PASS. The help text now exposes the non-interactive rules and copyable templates, and the missing-argument flows now fail with exit code 2 and example commands.

- [ ] **Step 7: Commit**

```bash
git add tests/test_cli.py ocr_flow/cli.py
git commit -m "feat(cli): add self-explaining non-interactive help and errors"
```

---

### Task 2: Turn interactive prompts into a short explanation-driven wizard

**Files:**
- Modify: `tests/test_cli.py:201-299`
- Modify: `ocr_flow/cli.py:125-223`
- Modify: `ocr_flow/cli.py:392-411`

- [ ] **Step 1: Add failing tests for auto detection and prompt explanations**

In `tests/test_cli.py`, replace `test_interactive_ask_each_pdf_type` and add the two new tests below it:

```python
def test_interactive_ask_each_pdf_type(self, monkeypatch):
    """Test ask_each for PDF type."""
    inputs = iter([4, 1, 2, 'Y'])  # ask_each, en, no translate

    def mock_prompt(*args, **kwargs):
        try:
            return next(inputs)
        except StopIteration:
            return 'Y'

    monkeypatch.setattr('click.prompt', mock_prompt)
    monkeypatch.setattr('click.echo', lambda *a, **kw: None)

    result = interactive_ask(is_batch=True)

    assert result['pdf_type'] == 'ask_each'


def test_interactive_single_file_supports_auto_choice(self, monkeypatch):
    """Test single-file interactive mode supports auto detection."""
    inputs = iter([3, 1, 1, 'Y'])
    echoed = []

    def mock_prompt(*args, **kwargs):
        try:
            return next(inputs)
        except StopIteration:
            return 'Y'

    monkeypatch.setattr('click.prompt', mock_prompt)
    monkeypatch.setattr('click.echo', lambda message='', **kwargs: echoed.append(message))

    result = interactive_ask(is_batch=False)

    assert result is not None
    assert result['pdf_type'] == 'auto'
    assert any('自动检测' in line for line in echoed)


def test_interactive_scanned_prompt_mentions_umi_ocr(self, monkeypatch):
    """Test scanned prompt mentions UMI OCR guidance."""
    inputs = iter([2, 1, 2, 'Y'])
    echoed = []

    def mock_prompt(*args, **kwargs):
        try:
            return next(inputs)
        except StopIteration:
            return 'Y'

    monkeypatch.setattr('click.prompt', mock_prompt)
    monkeypatch.setattr('click.echo', lambda message='', **kwargs: echoed.append(message))

    result = interactive_ask(is_batch=False)

    assert result is not None
    assert result['pdf_type'] == 'scanned'
    assert any('UMI OCR' in line for line in echoed)
    assert any('双语 PDF' in line for line in echoed)
```

- [ ] **Step 2: Run the targeted interactive tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli.py -k "test_interactive_ask_each_pdf_type or test_interactive_single_file_supports_auto_choice or test_interactive_scanned_prompt_mentions_umi_ocr" -v
```

Expected: FAIL because the current interactive flow does not offer `auto` in single-file mode, still uses `3` for `ask_each` in batch mode, and does not emit UMI OCR / bilingual PDF explanation lines.

- [ ] **Step 3: Replace the batch and single-file prompt text in `interactive_ask`**

Replace the `is_batch` and single-file prompt blocks in `ocr_flow/cli.py:136-208` with:

```python
    if is_batch:
        click.echo("批量处理模式:\n")

        # PDF type
        click.echo("  PDF 类型:")
        click.echo("  (1) 全部文字版 - PDF 已有文字层，通常不需要 OCR")
        click.echo("  (2) 全部扫描版 - PDF 是扫描件，需要 UMI OCR")
        click.echo("  (3) 全部自动检测 - 不确定时推荐")
        click.echo("  (4) 逐个询问")
        pdf_choice = click.prompt("  选择", type=click.INT, default=3)

        if pdf_choice == 1:
            options['pdf_type'] = 'text'
        elif pdf_choice == 2:
            options['pdf_type'] = 'scanned'
        elif pdf_choice == 3:
            options['pdf_type'] = 'auto'
        else:
            options['pdf_type'] = 'ask_each'

        # Document language
        click.echo("\n  文档语言:")
        click.echo("  (1) 全部英文")
        click.echo("  (2) 全部中文")
        click.echo("  (3) 逐个询问")
        lang_choice = click.prompt("  选择", type=click.INT, default=1)

        if lang_choice == 1:
            options['language'] = 'en'
        elif lang_choice == 2:
            options['language'] = 'zh'
        else:
            options['language'] = 'ask_each'

        # Translate
        click.echo("\n  是否翻译:")
        click.echo("  (1) 全部翻译成中文 - 先生成双语 PDF，再继续生成 Markdown")
        click.echo("  (2) 全部不翻译 - 直接进入 Markdown 流程")
        click.echo("  (3) 逐个询问")
        trans_choice = click.prompt("  选择", type=click.INT, default=2)

        if trans_choice == 1:
            options['translate'] = True
        elif trans_choice == 2:
            options['translate'] = False
        else:
            options['translate'] = 'ask_each'

    else:
        # Single file mode
        click.echo("请确认以下信息:\n")

        # PDF type
        click.echo("  PDF 类型:")
        click.echo("  (1) 文字版 - PDF 已有文字层，通常不需要 OCR")
        click.echo("  (2) 扫描版 - PDF 是图片扫描件，需要 UMI OCR")
        click.echo("  (3) 自动检测 - 不确定时推荐")
        pdf_choice = click.prompt("  选择", type=click.INT, default=3)
        options['pdf_type'] = {1: 'text', 2: 'scanned', 3: 'auto'}[pdf_choice]

        if options['pdf_type'] == 'scanned':
            click.echo("  提示: 扫描版需要 UMI OCR，可先运行 ocr-flow doctor --ocr --start-ocr")

        # Document language
        click.echo("\n  文档语言:")
        click.echo("  (1) 英文")
        click.echo("  (2) 中文")
        lang_choice = click.prompt("  选择", type=click.INT, default=1)
        options['language'] = 'en' if lang_choice == 1 else 'zh'

        # Translate (skip if Chinese)
        if options['language'] == 'zh':
            options['translate'] = False
            click.echo("\n  文档为中文，跳过翻译")
        else:
            click.echo("\n  是否翻译:")
            click.echo("  (1) 是 - 先生成双语 PDF，再继续生成 Markdown")
            click.echo("  (2) 否 - 直接进入 Markdown 流程")
            trans_choice = click.prompt("  选择", type=click.INT, default=1)
            options['translate'] = (trans_choice == 1)
```

- [ ] **Step 4: Update the per-file batch prompts to match the new choices**

Replace the `ask_each_pdf_type` / `ask_each_translate` prompt block in `ocr_flow/cli.py:395-411` with:

```python
                if ask_each_pdf_type:
                    click.echo("  PDF 类型:")
                    click.echo("  (1) 文字版 - PDF 已有文字层，通常不需要 OCR")
                    click.echo("  (2) 扫描版 - PDF 是扫描件，需要 UMI OCR")
                    click.echo("  (3) 自动检测 - 不确定时推荐")
                    choice = click.prompt("  选择", type=click.INT, default=3)
                    file_pdf_type = {1: 'text', 2: 'scanned', 3: 'auto'}[choice]
                    if file_pdf_type == 'scanned':
                        click.echo("  提示: 扫描版需要 UMI OCR，可先运行 ocr-flow doctor --ocr --start-ocr")

                if ask_each_lang:
                    click.echo("  文档语言: (1) 英文  (2) 中文")
                    choice = click.prompt("  选择", type=click.INT, default=1)
                    file_lang = 'en' if choice == 1 else 'zh'

                if ask_each_translate:
                    if file_lang == 'zh':
                        file_translate = False
                    else:
                        click.echo("  是否翻译:")
                        click.echo("  (1) 是 - 先生成双语 PDF，再继续生成 Markdown")
                        click.echo("  (2) 否 - 直接进入 Markdown 流程")
                        choice = click.prompt("  选择", type=click.INT, default=1)
                        file_translate = (choice == 1)
```

- [ ] **Step 5: Run the targeted interactive tests to verify they pass**

Run:

```bash
uv run pytest tests/test_cli.py -k "test_interactive_ask_each_pdf_type or test_interactive_single_file_supports_auto_choice or test_interactive_scanned_prompt_mentions_umi_ocr" -v
```

Expected: PASS. Interactive mode now offers `auto` in single-file and per-file flows, uses `4` for `ask_each` in batch mode, and prints one-line explanations for OCR and bilingual-PDF consequences.

- [ ] **Step 6: Commit**

```bash
git add tests/test_cli.py ocr_flow/cli.py
git commit -m "feat(cli): add explanation-driven interactive prompts"
```

---

### Task 3: Make `doctor` print the next executable command

**Files:**
- Modify: `tests/test_cli.py:407-453`
- Modify: `ocr_flow/self_check.py:21-163`
- Modify: `ocr_flow/cli.py:14-35`
- Modify: `ocr_flow/cli.py:479-520`

- [ ] **Step 1: Replace the doctor tests with behavior that expects next-step guidance**

Replace the three tests in `TestDoctorCommand` with:

```python
@patch('ocr_flow.self_check.SelfCheck')
def test_doctor_basic(self, mock_check_class, runner, mock_config):
    """Test basic doctor command."""
    mock_checker = MagicMock()
    mock_checker.check_all.return_value = {
        'ghostscript': {'ok': True, 'message': 'Found'},
        'mineru_api': {'ok': True, 'message': 'Configured'},
    }
    mock_check_class.return_value = mock_checker

    result = runner.invoke(cli, ['doctor'])

    assert result.exit_code == 0
    assert 'All checks passed!' in result.output
    assert 'Next step command:' in result.output
    assert 'ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --no-translate -v' in result.output


@patch('ocr_flow.self_check.SelfCheck')
def test_doctor_with_ocr(self, mock_check_class, runner, mock_config):
    """Test doctor with --ocr flag."""
    mock_checker = MagicMock()
    mock_checker.check_umi_ocr.return_value = {
        'ok': False,
        'message': 'Service not running at http://127.0.0.1:1224. Start UMI OCR application.',
        'next_step': 'ocr-flow doctor --ocr --start-ocr',
    }
    mock_checker.check_ghostscript.return_value = {'ok': True, 'message': 'Found'}
    mock_checker.check_mineru_api.return_value = {'ok': True, 'message': 'OK'}
    mock_check_class.return_value = mock_checker

    result = runner.invoke(cli, ['doctor', '--ocr'])

    assert result.exit_code == 0
    assert 'Some checks failed.' in result.output
    assert 'Next step:' in result.output
    assert 'ocr-flow doctor --ocr --start-ocr' in result.output


@patch('ocr_flow.self_check.SelfCheck')
def test_doctor_with_translate(self, mock_check_class, runner, mock_config):
    """Test doctor with --translate flag."""
    mock_checker = MagicMock()
    mock_checker.check_all.return_value = {
        'ghostscript': {'ok': True, 'message': 'Found'},
        'mineru_api': {
            'ok': False,
            'message': 'API token not configured',
            'next_step': 'ocr-flow config',
        },
        'babeldoc': {
            'ok': False,
            'message': 'Not found. Install with: pip install BabelDOC or clone and use path config',
            'next_step': 'ocr-flow config',
        },
    }
    mock_check_class.return_value = mock_checker

    result = runner.invoke(cli, ['doctor', '--translate'])

    assert result.exit_code == 0
    assert 'Some checks failed.' in result.output
    assert 'Next step:' in result.output
    assert 'ocr-flow config' in result.output
```

- [ ] **Step 2: Run the targeted doctor tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli.py -k "test_doctor_basic or test_doctor_with_ocr or test_doctor_with_translate" -v
```

Expected: FAIL because `doctor` currently prints a status table plus a generic config hint, but does not render a success command or consume a structured `next_step` field.

- [ ] **Step 3: Add `next_step` fields to the relevant `SelfCheck` failures**

Replace the return values in `ocr_flow/self_check.py` as follows:

```python
    def check_mineru_api(self) -> Dict[str, Any]:
        """Check if MinerU API token is configured."""
        if not self.config or not self.config.mineru.api_token:
            return {
                'ok': False,
                'message': 'API token not configured',
                'next_step': 'ocr-flow config',
            }

        token = self.config.mineru.api_token
        if token and token != 'your-mineru-api-token-here':
            return {'ok': True, 'message': f'API token configured ({token[:10]}...)'}

        return {
            'ok': False,
            'message': 'API token not configured',
            'next_step': 'ocr-flow config',
        }
```

```python
            return {
                'ok': False,
                'message': f'Service not running at {url}. Start UMI OCR application.',
                'next_step': 'ocr-flow doctor --ocr --start-ocr',
            }
```

```python
                    return {
                        'ok': False,
                        'message': f'Service started but not responding at {url}',
                        'next_step': 'ocr-flow doctor --ocr --start-ocr',
                    }
                else:
                    return {
                        'ok': False,
                        'message': f"Service not running. {result['message']}",
                        'next_step': 'ocr-flow doctor --ocr --start-ocr',
                    }
```

```python
            if babel_path.exists():
                return {'ok': True, 'message': f'Found at {babel_path}'}
            else:
                return {
                    'ok': False,
                    'message': f'Path not found: {babel_path}',
                    'next_step': 'ocr-flow config',
                }
```

```python
        return {
            'ok': False,
            'message': 'Not found. Install with: pip install BabelDOC or clone and use path config',
            'next_step': 'ocr-flow config',
        }
```

- [ ] **Step 4: Add doctor follow-up render helpers and use them in `ocr_flow/cli.py`**

Insert these helpers below `raise_usage_with_examples(...)` in `ocr_flow/cli.py`:

```python
def doctor_success_commands(needs_translate: bool, needs_ocr: bool) -> list[str]:
    """Return the minimal verified commands for the current doctor scope."""
    if needs_ocr and needs_translate:
        return [SCANNED_TRANSLATE_COMMAND]
    if needs_ocr:
        return [SCANNED_NO_TRANSLATE_COMMAND]
    if needs_translate:
        return [TEXT_TRANSLATE_COMMAND]
    return [TEXT_NO_TRANSLATE_COMMAND]


def print_doctor_follow_up(results: Dict[str, Dict[str, Any]], needs_translate: bool, needs_ocr: bool) -> None:
    """Render next-step guidance after the doctor status table."""
    next_steps = []
    for result in results.values():
        if result.get('ok'):
            continue
        next_step = result.get('next_step')
        if next_step and next_step not in next_steps:
            next_steps.append(next_step)

    click.echo("")
    if next_steps:
        click.echo("Next step:")
        for step in next_steps:
            click.echo(f"  {step}")
        return

    click.echo("Next step command:")
    for command in doctor_success_commands(needs_translate=needs_translate, needs_ocr=needs_ocr):
        click.echo(f"  {command}")
```

Then replace the tail of `doctor()` in `ocr_flow/cli.py:514-520` with:

```python
    click.echo("")
    if all_passed:
        click.echo("All checks passed!")
    else:
        click.echo("Some checks failed.")

    print_doctor_follow_up(results, needs_translate=translate, needs_ocr=ocr)
```

- [ ] **Step 5: Run the targeted doctor tests to verify they pass**

Run:

```bash
uv run pytest tests/test_cli.py -k "test_doctor_basic or test_doctor_with_ocr or test_doctor_with_translate" -v
```

Expected: PASS. `doctor` now prints a verified next command on success and consumes `next_step` on failure instead of falling back to a generic config hint.

- [ ] **Step 6: Commit**

```bash
git add tests/test_cli.py ocr_flow/self_check.py ocr_flow/cli.py
git commit -m "feat(doctor): print next executable commands from self-check results"
```

---

### Task 4: Move Quick Start and translated artifact expectations to the top of the README

**Files:**
- Modify: `README.md:1-186`

- [ ] **Step 1: Insert the new AI-first opening block above `## 功能特性`**

Insert this block at the top of `README.md`, immediately after the one-line project description, and keep the existing `## 功能特性` / `## 安装` / `## 配置` sections below it:

```markdown
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
```

- [ ] **Step 2: Rewrite the old “非交互模式必需参数 / 常见错误及修正 / 使用方法” sections to use the same placeholders**

Replace the existing concrete examples under `README.md:132-226` so they consistently use angle-bracket placeholders instead of repo-specific sample filenames:

```markdown
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
```

- [ ] **Step 3: Verify that the first complete command now appears before installation details**

Run:

```bash
uv run python -c "from pathlib import Path; lines = Path('README.md').read_text(encoding='utf-8').splitlines(); print('\n'.join(f'{i+1}: {line}' for i, line in enumerate(lines[:80])))"
```

Expected: the output shows `## Quick Start` plus a full `ocr-flow process <input.pdf> -o <output_dir> ...` command before `## 安装`, and it also includes the `intermediate/*.dual.pdf` note in the early section.

- [ ] **Step 4: Run the CLI regression slice again after the docs rewrite**

Run:

```bash
uv run pytest tests/test_cli.py -k "process_help or requires_lang or requires_translate_flag or interactive or doctor" -v
```

Expected: PASS. The README reordering should not require further CLI changes, and this gives you a final regression check across the interfaces the README now points to.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(readme): front-load quick start and command repair guidance"
```

---

## Plan Self-Review

### Spec coverage

- README 首屏可发现性：Task 4
- `process --help` 的规则块和模板：Task 1
- non-interactive 缺参纠偏：Task 1
- interactive prompt 的后果说明：Task 2
- `doctor` 的下一步命令：Task 3
- 翻译中间产物位置说明：Task 4
- 不改 pipeline 主流程：已通过文件范围约束保证

### Placeholder scan

本计划没有使用 `TODO`、`TBD` 或 “similar to above” 之类占位描述。每个任务都给了具体文件、具体代码块、具体测试命令和期望结果。

### Type consistency

- 共享命令模板名称在所有任务中统一为：
  - `INTERACTIVE_COMMAND`
  - `TEXT_NO_TRANSLATE_COMMAND`
  - `TEXT_TRANSLATE_COMMAND`
  - `SCANNED_NO_TRANSLATE_COMMAND`
  - `SCANNED_TRANSLATE_COMMAND`
- `SelfCheck` 的扩展字段统一为 `next_step`
- CLI helper 名称统一为 `format_command_examples`、`raise_usage_with_examples`、`doctor_success_commands`、`print_doctor_follow_up`
