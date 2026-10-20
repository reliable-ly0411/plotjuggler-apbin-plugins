#!/usr/bin/env python3
"""Bind validated artifact bytes to a non-PR native-build run and exact source."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('Artifact must not contain symbolic links')
        if p.is_file() and p.name != 'provenance.json':
            result[p.relative_to(root).as_posix()] = {'size': p.stat().st_size, 'sha256': digest(p)}
    if not result:
        raise ValueError('No final artifact bytes to attest')
    return result


def record(root, target):
    root = Path(root)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    data = {'schema': 1, 'repository': os.environ['GITHUB_REPOSITORY'],
            'source_sha': sha, 'run_id': os.environ['GITHUB_RUN_ID'],
            'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
            'event': os.environ['GITHUB_EVENT_NAME'], 'target': target,
            'workflow_ref': os.environ['GITHUB_WORKFLOW_REF'],
            'workflow_sha': os.environ['GITHUB_WORKFLOW_SHA'], 'files': files(root)}
    (root / 'provenance.json').write_text(json.dumps(data, indent=2) + '\n')


def validate_run(run, repo, source_sha, branch, workflow):
    expected = {'head_sha': source_sha, 'head_branch': branch, 'path': workflow,
                'status': 'completed', 'conclusion': 'success', 'event': 'workflow_dispatch'}
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha):
        raise ValueError('Full source SHA required')
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError(f'Candidate run {key}: expected {value}, got {run.get(key)}')
    if run.get('repository', {}).get('full_name') != repo:
        raise ValueError('Candidate belongs to another repository')


def verify(root, run, source_sha, target):
    root = Path(root)
    data = json.loads((root / 'provenance.json').read_text())
    expected = {'schema': 1, 'repository': run['repository']['full_name'],
                'source_sha': source_sha, 'run_id': str(run['id']),
                'run_attempt': str(run['run_attempt']), 'event': 'workflow_dispatch',
                'target': target, 'workflow_sha': source_sha,
                'workflow_ref': run['repository']['full_name'] + '/' + run['path'] + '@refs/heads/' + run['head_branch']}
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError('Artifact provenance mismatch: ' + key)
    if data.get('files') != files(root):
        raise ValueError('Artifact bytes/paths differ from successful native-build receipt')
    return data


if __name__ == '__main__':
    record(sys.argv[1], sys.argv[2])
