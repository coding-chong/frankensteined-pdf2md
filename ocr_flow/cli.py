#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OCR Flow CLI entry point."""

import click
from pathlib import Path
from . import __version__


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
        click.echo("  (1) 全部文字版")
        click.echo("  (2) 全部扫描版")
        click.echo("  (3) 逐个询问")
        pdf_choice = click.prompt("  选择", type=click.INT, default=1)

        if pdf_choice == 1:
            options['pdf_type'] = 'text'
        elif pdf_choice == 2:
            options['pdf_type'] = 'scanned'
        else:
            options['pdf_type'] = 'ask_each'  # Will ask per file

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
        click.echo("  (1) 全部翻译成中文")
        click.echo("  (2) 全部不翻译")
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
        click.echo("  (1) 文字版")
        click.echo("  (2) 扫描版")
        pdf_choice = click.prompt("  选择", type=click.INT, default=1)
        options['pdf_type'] = 'text' if pdf_choice == 1 else 'scanned'

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
            click.echo("  (1) 是，翻译成中文")
            click.echo("  (2) 否，保持原文")
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


@cli.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), help='Output directory')
@click.option('--config', type=click.Path(), help='Config file path')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.option('--non-interactive', is_flag=True, help='Non-interactive mode')
@click.option('--pdf-type', type=click.Choice(['text', 'scanned']), help='PDF type (non-interactive mode)')
@click.option('--lang', type=click.Choice(['en', 'zh']), help='Document language (non-interactive mode)')
@click.option('--translate/--no-translate', default=None, help='Translate to Chinese (non-interactive mode)')
def process(input_path: str, output: str, config: str, verbose: bool,
            non_interactive: bool, pdf_type: str, lang: str, translate: bool):
    """Process PDF file(s) to Markdown.

    INPUT_PATH: PDF file or directory containing PDF files
    """
    from pathlib import Path
    from .pipeline import Pipeline
    from .config import Config

    input_path = Path(input_path)

    # Load config
    cfg = Config.load(config_path=Path(config) if config else None)

    # Create output directory
    output_dir = Path(output) if output else Path.cwd() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine processing mode
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = list(input_path.glob("*.pdf"))
        if not files:
            click.echo(f"No PDF files found in {input_path}")
            return
    else:
        click.echo(f"Invalid input path: {input_path}")
        return

    click.echo(f"\n[INFO] Found {len(files)} PDF file(s)\n")

    # Interactive mode: ask for options
    if not non_interactive:
        options = interactive_ask(len(files) > 1)
        if options is None:
            click.echo("Cancelled.")
            return
        pdf_type = options['pdf_type']
        lang = options['language']
        translate = options['translate']

    # Non-interactive mode: use provided options
    if not pdf_type:
        click.echo("--pdf-type is required in non-interactive mode")
        return
    if not lang:
        click.echo("--lang is required in non-interactive mode")
        return
    if translate is None:
        click.echo("--translate or --no-translate is required in non-interactive mode")
        return

    # Run pipeline
    pipeline = Pipeline(cfg, verbose=verbose)
    for pdf_file in files:
        click.echo(f"Processing: {pdf_file}")
        try:
            result = pipeline.run(
                pdf_file,
                output_dir,
                pdf_type=pdf_type,
                language=lang,
                translate=translate
            )
            click.echo(f"Completed: {result}")
        except Exception as e:
            click.echo(f"Error processing {pdf_file}: {e}")


@cli.command()
def config():
    """Configure OCR Flow (API keys, paths, etc.)."""
    from .config import Config
    Config.configure_interactive()


@cli.command()
@click.option('--fix', is_flag=True, help='Try to fix issues')
def doctor(fix: bool):
    """Check system dependencies and configuration."""
    from .self_check import SelfCheck
    from .config import Config

    # Load config
    cfg = Config.load()

    checker = SelfCheck(config=cfg)
    results = checker.check_all()

    click.echo("\n=== OCR Flow System Check ===\n")

    all_passed = True
    for name, result in results.items():
        status = "[OK]" if result["ok"] else "[FAIL]"
        click.echo(f"  {status} {name}: {result['message']}")
        if not result["ok"]:
            all_passed = False

    click.echo("")
    if all_passed:
        click.echo("All checks passed!")
    else:
        click.echo("Some checks failed. Run 'ocr-flow config' to configure.")


if __name__ == '__main__':
    cli()
