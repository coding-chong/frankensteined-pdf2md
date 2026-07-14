#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OCR Flow CLI entry point."""

import sys
import time
import subprocess
import click
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from . import __version__
from .state import State, StateManager

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
    has_failures = any(not result.get('ok') for result in results.values())
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

    if has_failures:
        click.echo("Next step:")
        click.echo("  Resolve the failed checks above before running ocr-flow process.")
        return

    click.echo("Next step command:")
    for command in doctor_success_commands(needs_translate=needs_translate, needs_ocr=needs_ocr):
        click.echo(f"  {command}")


def detect_unfinished_task(work_dir: Path) -> Optional[Dict[str, Any]]:
    """Detect unfinished task in output directory.

    Args:
        work_dir: Working directory to check for .state.json

    Returns:
        Dict with state info if unfinished, None if completed or no state
    """

    state_manager = StateManager(work_dir)
    if not state_manager.has_state():
        return None

    state = state_manager.state or State.load(state_manager.state_path)
    if not state:
        return None

    if state.is_completed():
        return None

    # Analyze step status
    current_step = state.current_step or "unknown"

    # Count completed/failed/pending for mineru step (most common partial case)
    mineru_step = state.steps.get('mineru')
    if mineru_step:
        completed = len(mineru_step.completed) if mineru_step.completed else 0
        failed_count = len(mineru_step.failed) if mineru_step.failed else 0
        total = state.total_pages or 0
        pending = total - completed - failed_count

        return {
            'state': state,
            'state_manager': state_manager,
            'current_step': current_step,
            'total': total,
            'completed': completed,
            'failed': list(mineru_step.failed.keys()) if mineru_step.failed else [],
            'pending': pending,
        }

    # For other steps, just report current step
    return {
        'state': state,
        'state_manager': state_manager,
        'current_step': current_step,
        'total': 0,
        'completed': 0,
        'failed': [],
        'pending': 0,
    }


def show_recovery_menu(state_info: Dict[str, Any]) -> Optional[str]:
    """Show recovery menu and return user choice.

    Returns:
        'continue' | 'retry' | 'continue_retry' | 'restart' | 'cancel'
    """
    console.print("\n[bold yellow][*] 检测到上次未完成的任务:[/bold yellow]")
    console.print(f"   步骤: {state_info['current_step']}")

    if state_info['total'] > 0:
        console.print(f"   [green][OK] 已完成:[/green] {state_info['completed']}/{state_info['total']}")
        if state_info['failed']:
            console.print(f"   [red][X] 失败:[/red] {', '.join(state_info['failed'])}")
        if state_info['pending'] > 0:
            console.print(f"   [yellow]⏸️ 未开始:[/yellow] {state_info['pending']} 个文件")

    console.print("\n   [bold]恢复选项:[/bold]")
    console.print("   (1) 继续 - 处理未开始的文件")
    if state_info['failed']:
        console.print("   (2) 重试失败 - 只处理失败的文件")
        console.print("   (3) 继续 + 重试 - 处理失败的和未开始的")
        console.print("   (4) 重来 - 删除所有，重新开始")
        console.print("   (5) 取消")
        choices = ['1', '2', '3', '4', '5']
    else:
        console.print("   (2) 重来 - 删除所有，重新开始")
        console.print("   (3) 取消")
        choices = ['1', '2', '3']

    choice = click.prompt("\n   选择", type=click.Choice(choices), default='1')

    if not state_info['failed']:
        # Simplified menu
        if choice == '1':
            return 'continue'
        elif choice == '2':
            return 'restart'
        else:
            return 'cancel'
    else:
        # Full menu
        if choice == '1':
            return 'continue'
        elif choice == '2':
            return 'retry'
        elif choice == '3':
            return 'continue_retry'
        elif choice == '4':
            return 'restart'
        else:
            return 'cancel'


def interactive_ask(is_batch: bool = False) -> dict:
    """Interactive mode: ask user for processing options.

    Args:
        is_batch: Whether this is a batch processing run

    Returns:
        Dict with pdf_type, language, translate, or None if cancelled
    """
    options = {}

    if is_batch:
        click.echo("批量处理模式:\n")

        # PDF type
        click.echo("  PDF 类型:")
        click.echo("  (1) 全部文字版 - PDF 已有文字层，通常不需要 OCR")
        click.echo("  (2) 全部扫描版 - PDF 是扫描件，需要 UMI OCR")
        click.echo("  (3) 全部自动检测 - 不确定时推荐")
        click.echo("  (4) 逐个询问")
        pdf_choice = click.prompt("  选择", type=click.IntRange(1, 3), default=3)

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
        pdf_choice = click.prompt("  选择", type=click.IntRange(1, 3), default=3)
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

    # Confirmation
    click.echo("")
    if options.get('pdf_type') not in ['ask_each', None]:
        click.echo(f"  PDF 类型: {options.get('pdf_type', 'ask_each')}")
    if options.get('language') not in ['ask_each', None]:
        click.echo(f"  文档语言: {options.get('language', 'ask_each')}")
    if options.get('translate') not in ['ask_each', None]:
        click.echo(f"  是否翻译: {'是' if options.get('translate') else '否'}")

    confirm = click.prompt("\n  确认开始处理？[Y/n]", default='Y')
    if confirm.lower() not in ['y', 'yes', '']:
        return None

    return options


@click.group()
@click.version_option(version=__version__)
def cli():
    """OCR Flow - PDF to Markdown converter for chip manuals and datasheets."""
    pass


@cli.group()
def runtime():
    """Manage the pinned BabelDOC Runtime Profiles."""
    pass


@runtime.command()
@click.option(
    '--profile',
    type=click.Choice(['cpu-safe', 'windows-directml']),
    default='cpu-safe',
    show_default=True,
)
@click.option(
    '--path',
    'checkout_path',
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help='Destructively normalize this BabelDOC Git worktree instead of the managed runtime.',
)
def setup(profile: str, checkout_path: Optional[Path]):
    """Acquire and install the tested BabelDOC Runtime Profile."""
    from .babeldoc_runtime import (
        bootstrap,
        load_manifest,
        reconcile_external_checkout,
        reconcile_managed_checkout,
    )

    manifest = load_manifest()
    try:
        managed = checkout_path is None
        checkout = (
            reconcile_managed_checkout(manifest)
            if managed
            else reconcile_external_checkout(checkout_path, manifest)
        )
        bootstrap(checkout, manifest, profile, managed=managed)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error


@runtime.command()
def status():
    """Show local runtime readiness and the advisory upstream release status."""
    from .babeldoc_runtime import load_manifest, status_lines

    lines, _ = status_lines(load_manifest())
    click.echo("\n".join(lines))


@runtime.command()
@click.option('--input', 'input_path', required=True, type=click.Path(exists=True, dir_okay=False))
@click.option(
    '--profile',
    type=click.Choice(['cpu-safe', 'windows-directml']),
    default='cpu-safe',
    show_default=True,
)
@click.option(
    '--path',
    'checkout_path',
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help='Smoke-test this previously normalized external BabelDOC worktree.',
)
def smoke(input_path: str, profile: str, checkout_path: Optional[Path]):
    """Run local layout inference against a verified BabelDOC Runtime."""
    from .babeldoc_runtime import load_manifest, smoke as smoke_runtime
    from .runtime import (
        MANAGED_BABELDOC_PATH,
        external_runtime_readiness,
        managed_runtime_readiness,
    )

    if checkout_path is None:
        checkout = MANAGED_BABELDOC_PATH
        ready, message = managed_runtime_readiness(profile)
    else:
        checkout = checkout_path.expanduser().resolve()
        ready, message = external_runtime_readiness(checkout, profile)
    if not ready:
        raise click.ClickException(message)
    try:
        smoke_runtime(checkout, load_manifest(), profile, Path(input_path))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error


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
@click.option('--ocr-timeout', type=click.INT, help='Override OCR timeout in seconds for scanned PDFs. Large scanned PDFs auto-extend this by default.')
@click.option('--ocr-language', type=str, help='Override UMI OCR model path for scanned PDFs. By default, scanned PDFs pick the OCR model from --lang.')
@click.option('--open-output/--no-open-output', default=None, help='Open output directory after completion. Defaults to prompt in interactive mode and disabled in non-interactive mode.')
@click.option('--recovery', type=click.Choice(['continue', 'retry', 'continue_retry', 'restart']), default=None, help='Recovery mode for non-interactive mode: continue, retry, continue_retry, restart')
def process(input_path: str, output: str, config: str, verbose: bool,
            non_interactive: bool, pdf_type: str, lang: str, translate: bool, compress: bool,
            ocr_timeout: int, ocr_language: str, open_output: bool, recovery: str):
    """Process PDF file(s) to Markdown.

    INPUT_PATH: PDF file or directory containing PDF files

    Non-interactive mode requires:
      --lang
      --translate or --no-translate

    \b
    Common examples:
      ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type text --lang en --translate -v
      ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type scanned --lang en --no-translate -v
      ocr-flow process <input.pdf> -o <output_dir> --non-interactive --pdf-type scanned --lang zh --no-translate -v
      ocr-flow process <input.pdf> -o <output_dir> -v
    """
    import shutil
    from datetime import datetime
    from .pipeline import Pipeline
    from .config import Config
    input_path = Path(input_path)

    # S2.3: Check for first-time config
    config_path = Path(config).expanduser() if config else Config.get_config_path()
    if not config_path.exists():
        if non_interactive:
            raise click.UsageError(
                "configuration file not found for non-interactive mode.\n\n"
                "Next step:\n"
                "  ocr-flow config"
            )
        console.print("\n[bold yellow]⚠️ 未检测到配置文件，开始配置向导...[/bold yellow]\n")
        Config.configure_interactive()

        if not click.confirm("\n是否继续处理?", default=True):
            return

    # Load config
    cfg = Config.load(config_path=config_path)

    # Create output directory
    output_dir = Path(output) if output else Path.cwd() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine processing mode
    if input_path.is_file():
        files = [input_path]
        is_batch = False
    elif input_path.is_dir():
        files = list(input_path.glob("*.pdf"))
        if not files:
            click.echo(f"No PDF files found in {input_path}")
            return
        is_batch = len(files) > 1
    else:
        click.echo(f"Invalid input path: {input_path}")
        return

    console.print(f"\n[bold][*] 发现 {len(files)} 个 PDF 文件[/bold]\n")

    # S1.1: Check for unfinished task in output directory
    recovery_mode = None
    state_info = detect_unfinished_task(output_dir / datetime.now().strftime("%Y%m%d_%H%M%S"))

    # Look for any existing state file in output_dir subdirectories
    for subdir in output_dir.iterdir():
        if subdir.is_dir():
            for subsubdir in subdir.iterdir():
                if subsubdir.is_dir():
                    potential_state = subsubdir / '.state.json'
                    if potential_state.exists():
                        state_info = detect_unfinished_task(subsubdir)
                        if state_info:
                            if non_interactive:
                                if recovery:
                                    recovery_mode = recovery
                                    console.print(f"\n[bold yellow][*] 检测到上次未完成的任务，使用恢复模式: {recovery_mode}[/bold yellow]")
                                    if recovery_mode == 'restart':
                                        shutil.rmtree(subsubdir)
                                        console.print("[yellow]已删除，将重新开始[/yellow]")
                                    break
                                continue

                            recovery_mode = show_recovery_menu(state_info)
                            if recovery_mode == 'cancel':
                                return
                            elif recovery_mode == 'restart':
                                if click.confirm(f"确认删除 {subsubdir}?", default=False):
                                    shutil.rmtree(subsubdir)
                                    console.print("[yellow]已删除，将重新开始[/yellow]")
                            break
            if recovery_mode:
                break

    # Interactive mode: ask for options
    ask_each_pdf_type = False
    ask_each_lang = False
    ask_each_translate = False

    if not non_interactive:
        options = interactive_ask(is_batch)
        if options is None:
            click.echo("Cancelled.")
            return

        # S2.1: Handle "ask_each" options for batch processing
        if is_batch:
            if options.get('pdf_type') == 'ask_each':
                ask_each_pdf_type = True
                pdf_type = None  # Will ask per file
            else:
                pdf_type = options['pdf_type']

            if options.get('language') == 'ask_each':
                ask_each_lang = True
                lang = None
            else:
                lang = options['language']

            if options.get('translate') == 'ask_each':
                ask_each_translate = True
                translate = None
            else:
                translate = options['translate']
        else:
            pdf_type = options['pdf_type']
            lang = options['language']
            translate = options['translate']

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

    # Run pipeline with progress bar
    pipeline = Pipeline(cfg, verbose=verbose)
    success_count = 0
    failed_count = 0
    failed_files = []
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        disable=len(files) == 1  # No progress bar for single file
    ) as progress:
        task = progress.add_task("[cyan]Processing PDFs...", total=len(files))

        for pdf_file in files:
            progress.update(task, description=f"[cyan]Processing: {pdf_file.name}")

            # S2.1: Ask per file if needed
            file_pdf_type = pdf_type
            file_lang = lang
            file_translate = translate

            if ask_each_pdf_type or ask_each_lang or ask_each_translate:
                console.print(f"\n[bold][*] {pdf_file.name}[/bold]")

                if ask_each_pdf_type:
                    click.echo("  PDF 类型:")
                    click.echo("  (1) 文字版 - PDF 已有文字层，通常不需要 OCR")
                    click.echo("  (2) 扫描版 - PDF 是扫描件，需要 UMI OCR")
                    click.echo("  (3) 自动检测 - 不确定时推荐")
                    choice = click.prompt("  选择", type=click.IntRange(1, 3), default=3)
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

            # Auto-detect PDF type if needed
            if file_pdf_type == 'auto':
                from .steps.split import detect_pdf_type
                file_pdf_type = detect_pdf_type(pdf_file)
                if verbose:
                    console.print(f"[dim][INFO][/dim] Auto-detected PDF type: [bold]{file_pdf_type}[/bold]")

            try:
                result = pipeline.run(
                    pdf_file,
                    output_dir,
                    pdf_type=file_pdf_type,
                    language=file_lang,
                    translate=file_translate,
                    compress=compress,
                    recovery_mode=recovery_mode,
                    state_info=state_info if recovery_mode else None,
                    ocr_timeout=ocr_timeout,
                    ocr_language=ocr_language,
                )
                console.print(f"[green][OK] Done:[/green] {pdf_file.name} -> {result}")
                success_count += 1
            except Exception as e:
                console.print(f"[red][X] Error:[/red] {pdf_file.name}: {e}")
                failed_count += 1
                failed_files.append(pdf_file.name)

            progress.advance(task)

    # S2.4: Show completion statistics
    elapsed_time = time.time() - start_time

    console.print(f"\n[bold]{'═' * 40}[/bold]")
    console.print("[bold green]处理完成！[/bold green]")
    console.print(f"  [green][OK] 成功:[/green] {success_count} 个文件")
    if failed_count > 0:
        console.print(f"  [red][X] 失败:[/red] {failed_count} 个文件")
        for f in failed_files:
            console.print(f"      - {f}")
    console.print(f"  [T] 耗时: {elapsed_time:.1f} 秒")
    console.print(f"[bold]{'═' * 40}[/bold]\n")

    should_open_output = open_output
    if should_open_output is None and not non_interactive:
        should_open_output = click.confirm("是否打开输出目录?", default=True)

    if should_open_output:
        import subprocess
        try:
            if sys.platform == 'win32':
                subprocess.run(['explorer', str(output_dir)], check=False)
            elif sys.platform == 'darwin':
                subprocess.run(['open', str(output_dir)], check=False)
            else:
                subprocess.run(['xdg-open', str(output_dir)], check=False)
        except (OSError, subprocess.SubprocessError) as e:
            console.print(f"[yellow]无法打开目录: {e}[/yellow]")


@cli.command()
def config():
    """Configure OCR Flow (API keys, paths, etc.)."""
    from .config import Config
    Config.configure_interactive()


@cli.command()
@click.option('--fix', is_flag=True, help='Try to fix issues')
@click.option('--translate', is_flag=True, help='Check translation dependencies (BabelDOC)')
@click.option('--ocr', is_flag=True, help='Check OCR dependencies (UMI OCR)')
@click.option('--start-ocr', is_flag=True, help='Auto-start UMI OCR if not running')
def doctor(fix: bool, translate: bool, ocr: bool, start_ocr: bool):
    """Check system dependencies and configuration."""
    from .self_check import SelfCheck
    from .config import Config

    # Load config
    cfg = Config.load()

    checker = SelfCheck(config=cfg)

    # Check UMI OCR with auto-start option
    if ocr:
        umi_result = checker.check_umi_ocr(auto_start=start_ocr)
        results = {
            'ghostscript': checker.check_ghostscript(),
            'mineru_api': checker.check_mineru_api(),
            'umi_ocr': umi_result
        }
        if translate:
            results['babeldoc'] = checker.check_babeldoc()
    else:
        results = checker.check_all(needs_ocr=ocr, needs_translate=translate)

    click.echo("\n=== OCR Flow System Check ===\n")

    all_passed = True
    for name, result in results.items():
        status = "[OK]" if result["ok"] else "[FAIL]"
        message = result['message']
        if result.get('started'):
            message += " (auto-started)"
        click.echo(f"  {status} {name}: {message}")
        if not result["ok"]:
            all_passed = False

    click.echo("")
    if all_passed:
        click.echo("All checks passed!")
    else:
        click.echo("Some checks failed.")

    print_doctor_follow_up(results, needs_translate=translate, needs_ocr=ocr)


if __name__ == '__main__':
    cli()
