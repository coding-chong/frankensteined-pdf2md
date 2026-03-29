#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""State management for OCR Flow - handles resume/retry logic."""

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import shutil

logger = logging.getLogger('ocr_flow')


@dataclass
class StepStatus:
    """Status of a single processing step."""
    status: str = "pending"  # pending, running, completed, partial, failed, skipped
    output: Optional[str] = None
    output_dir: Optional[str] = None
    files: List[str] = field(default_factory=list)
    completed: List[int] = field(default_factory=list)
    failed: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retries: int = 0


@dataclass
class State:
    """Processing state for a single PDF file."""
    version: int = 1
    source_path: str = ""
    source_size: int = 0
    source_sha256: str = ""
    options: Dict[str, Any] = field(default_factory=dict)
    total_pages: int = 0
    current_step: str = ""
    steps: Dict[str, StepStatus] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    @classmethod
    def create(cls, source_path: Path, options: Dict[str, Any]) -> 'State':
        """Create a new state for processing."""
        source_path = Path(source_path)

        # Calculate SHA256
        sha256 = hashlib.sha256()
        with open(source_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)

        return cls(
            source_path=str(source_path),
            source_size=source_path.stat().st_size,
            source_sha256=sha256.hexdigest(),
            options=options,
        )

    @classmethod
    def load(cls, state_path: Path) -> Optional['State']:
        """Load state from file."""
        if not state_path.exists():
            return None

        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # Corrupted state file - log warning and return None
            logger.warning(f"Corrupted state file {state_path}: {e}. Starting fresh.")
            return None

        # Convert step dicts to StepStatus objects
        steps = {}
        for name, step_data in data.get('steps', {}).items():
            steps[name] = StepStatus(**step_data)

        state = cls(
            version=data.get('version', 1),
            source_path=data.get('source_path', ''),
            source_size=data.get('source_size', 0),
            source_sha256=data.get('source_sha256', ''),
            options=data.get('options', {}),
            total_pages=data.get('total_pages', 0),
            current_step=data.get('current_step', ''),
            steps=steps,
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', ''),
        )
        return state

    def save(self, state_path: Path):
        """Save state to file."""
        self.updated_at = datetime.now().isoformat()

        # Convert to dict
        data = {
            'version': self.version,
            'source_path': self.source_path,
            'source_size': self.source_size,
            'source_sha256': self.source_sha256,
            'options': self.options,
            'total_pages': self.total_pages,
            'current_step': self.current_step,
            'steps': {name: asdict(step) for name, step in self.steps.items()},
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def update_step(self, step_name: str, status: str = None, **kwargs):
        """Update a step's status."""
        if step_name not in self.steps:
            self.steps[step_name] = StepStatus()

        step = self.steps[step_name]
        if status:
            step.status = status

        for key, value in kwargs.items():
            if hasattr(step, key):
                setattr(step, key, value)

        self.current_step = step_name
        self.updated_at = datetime.now().isoformat()

    def get_step_status(self, step_name: str) -> StepStatus:
        """Get status of a step."""
        if step_name not in self.steps:
            return StepStatus()
        return self.steps[step_name]

    def is_completed(self) -> bool:
        """Check if all steps are completed."""
        for step in self.steps.values():
            if step.status not in ('completed', 'skipped'):
                return False
        return True

    def get_pending_steps(self) -> List[str]:
        """Get list of steps that need to run."""
        step_order = ['ocr', 'translate', 'split', 'compress', 'mineru', 'format_fix', 'image_download']
        pending = []
        for step in step_order:
            if step not in self.steps:
                pending.append(step)
            elif self.steps[step].status in ('pending', 'failed', 'partial'):
                pending.append(step)
        return pending


class StateManager:
    """Manages state files and recovery logic."""

    STATE_FILE = '.state.json'
    BACKUP_DIR = '.backup'

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.state_path = self.output_dir / self.STATE_FILE
        self.backup_dir = self.output_dir / self.BACKUP_DIR
        self.state: Optional[State] = None

    def has_state(self) -> bool:
        """Check if state file exists."""
        return self.state_path.exists()

    def load_or_create(self, source_path: Path, options: Dict[str, Any]) -> State:
        """Load existing state or create new one."""
        if self.has_state():
            self.state = State.load(self.state_path)
            # Validate source matches
            if self.state and self.state.source_path == str(source_path):
                return self.state

        # Create new state
        self.state = State.create(source_path, options)
        self.state.save(self.state_path)
        return self.state

    def save(self):
        """Save current state."""
        if self.state:
            self.state.save(self.state_path)

    def backup_file(self, step_name: str, file_path: Path):
        """Backup an intermediate file."""
        backup_step_dir = self.backup_dir / step_name
        backup_step_dir.mkdir(parents=True, exist_ok=True)

        dest = backup_step_dir / file_path.name
        shutil.copy2(file_path, dest)

    def get_backup_file(self, step_name: str, filename: str) -> Optional[Path]:
        """Get a backup file if exists."""
        backup_path = self.backup_dir / step_name / filename
        if backup_path.exists():
            return backup_path
        return None

    def restore_from_backup(self, step_name: str, filename: str, dest: Path) -> bool:
        """Restore a file from backup."""
        backup_path = self.get_backup_file(step_name, filename)
        if backup_path:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, dest)
            return True
        return False

    def get_intermediate_file(self, step_name: str, filename: str, work_dir: Path) -> Optional[Path]:
        """Get intermediate file, preferring work dir, falling back to backup."""
        # Try work directory first
        work_path = work_dir / filename
        if work_path.exists():
            return work_path

        # Try backup
        return self.get_backup_file(step_name, filename)
