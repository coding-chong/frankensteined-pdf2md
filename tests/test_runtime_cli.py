"""Tests for the user-facing BabelDOC Runtime commands."""

import subprocess

from click.testing import CliRunner

from ocr_flow.cli import cli


def test_runtime_status_renders_advisory_release_result(monkeypatch):
    monkeypatch.setattr('ocr_flow.babeldoc_runtime.status_lines', lambda _manifest: ((
        'Supported BabelDOC: v0.6.3',
        'Upstream release check: v0.6.4 is newer',
    ), False))

    result = CliRunner().invoke(cli, ['runtime', 'status'])

    assert result.exit_code == 0
    assert 'v0.6.4 is newer' in result.output


def test_runtime_setup_reconciles_managed_checkout(monkeypatch, tmp_path):
    checkout = tmp_path / 'BabelDOC'
    called = {}
    manifest = {'version': '0.6.3'}

    monkeypatch.setattr('ocr_flow.babeldoc_runtime.load_manifest', lambda: manifest)
    monkeypatch.setattr('ocr_flow.babeldoc_runtime.reconcile_managed_checkout', lambda _manifest: checkout)

    def fake_bootstrap(path, received_manifest, profile, *, managed):
        called.update(path=path, manifest=received_manifest, profile=profile, managed=managed)

    monkeypatch.setattr('ocr_flow.babeldoc_runtime.bootstrap', fake_bootstrap)

    result = CliRunner().invoke(cli, ['runtime', 'setup', '--profile', 'cpu-safe'])

    assert result.exit_code == 0
    assert called == {
        'path': checkout,
        'manifest': manifest,
        'profile': 'cpu-safe',
        'managed': True,
    }


def test_runtime_setup_reconciles_explicit_external_checkout(monkeypatch, tmp_path):
    checkout = tmp_path / 'BabelDOC'
    checkout.mkdir()
    called = {}
    manifest = {'version': '0.6.3'}

    monkeypatch.setattr('ocr_flow.babeldoc_runtime.load_manifest', lambda: manifest)
    monkeypatch.setattr(
        'ocr_flow.babeldoc_runtime.reconcile_external_checkout',
        lambda path, _manifest: called.setdefault('reconciled_path', path) or checkout,
    )

    def fake_bootstrap(path, received_manifest, profile, *, managed):
        called.update(path=path, manifest=received_manifest, profile=profile, managed=managed)

    monkeypatch.setattr('ocr_flow.babeldoc_runtime.bootstrap', fake_bootstrap)

    result = CliRunner().invoke(
        cli, ['runtime', 'setup', '--path', str(checkout), '--profile', 'cpu-safe']
    )

    assert result.exit_code == 0
    assert called == {
        'reconciled_path': checkout,
        'path': checkout,
        'manifest': manifest,
        'profile': 'cpu-safe',
        'managed': False,
    }


def test_runtime_smoke_requires_setup(monkeypatch, tmp_path):
    input_path = tmp_path / 'input.pdf'
    input_path.write_bytes(b'pdf')
    monkeypatch.setattr(
        'ocr_flow.runtime.managed_runtime_readiness',
        lambda *_args: (False, 'Managed BabelDOC Runtime is not installed. Run `ocr-flow runtime setup`.'),
    )

    result = CliRunner().invoke(cli, ['runtime', 'smoke', '--input', str(input_path)])

    assert result.exit_code != 0
    assert 'runtime setup' in result.output


def test_runtime_smoke_renders_subprocess_failure(monkeypatch, tmp_path):
    input_path = tmp_path / 'input.pdf'
    input_path.write_bytes(b'pdf')
    monkeypatch.setattr(
        'ocr_flow.runtime.managed_runtime_readiness',
        lambda *_args: (True, 'Managed BabelDOC Runtime ready'),
    )
    monkeypatch.setattr(
        'ocr_flow.babeldoc_runtime.smoke',
        lambda *_args: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ['uv'])),
    )

    result = CliRunner().invoke(cli, ['runtime', 'smoke', '--input', str(input_path)])

    assert result.exit_code != 0
    assert 'NameError' not in result.output
    assert 'returned non-zero exit status 1' in result.output


def test_runtime_smoke_uses_verified_external_checkout(monkeypatch, tmp_path):
    checkout = tmp_path / 'BabelDOC'
    checkout.mkdir()
    input_path = tmp_path / 'input.pdf'
    input_path.write_bytes(b'pdf')
    called = {}

    monkeypatch.setattr(
        'ocr_flow.runtime.external_runtime_readiness',
        lambda path, profile: (called.update(ready_path=path, profile=profile) or (True, 'ready')),
    )
    monkeypatch.setattr(
        'ocr_flow.babeldoc_runtime.smoke',
        lambda path, manifest, profile, source: called.update(
            smoke_path=path, manifest=manifest, smoke_profile=profile, source=source
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            'runtime', 'smoke', '--path', str(checkout), '--input', str(input_path),
            '--profile', 'cpu-safe',
        ],
    )

    assert result.exit_code == 0
    assert called['ready_path'] == checkout.resolve()
    assert called['smoke_path'] == checkout.resolve()
    assert called['profile'] == 'cpu-safe'


def test_runtime_smoke_rejects_unprepared_external_checkout(monkeypatch, tmp_path):
    checkout = tmp_path / 'BabelDOC'
    checkout.mkdir()
    input_path = tmp_path / 'input.pdf'
    input_path.write_bytes(b'pdf')
    monkeypatch.setattr(
        'ocr_flow.runtime.external_runtime_readiness',
        lambda *_args: (False, 'Run `ocr-flow runtime setup --path C:/BabelDOC`.'),
    )

    result = CliRunner().invoke(
        cli, ['runtime', 'smoke', '--path', str(checkout), '--input', str(input_path)]
    )

    assert result.exit_code != 0
    assert 'runtime setup --path' in result.output
