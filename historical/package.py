#!/usr/bin/env python3
"""Collect an unmodified upstream-tag binary and its build identity."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SOURCES = {'v1.0.0': '30f0afde2082b18fb4fec0e79a5c8282eb14f308',
           'v1.1.0': '399136d91394fc838e813147438e822d8418233c'}

def asset_name(tag, platform, variant):
    if tag not in SOURCES or variant not in ('no_units', 'with_units'):
        raise ValueError('Unknown upstream build')
    if platform == 'windows-2022':
        if tag != 'v1.1.0' or variant != 'no_units':
            raise ValueError('Not part of the upstream release asset matrix')
        return 'DataAPBin_no_units.dll'
    if platform != 'ubuntu-22.04':
        raise ValueError('Unknown platform')
    suffix = '_v1.0.0' if tag == 'v1.0.0' else ''
    return f'libDataAPBin_{variant}{suffix}.so'

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

def main(tag, platform, variant):
    name = asset_name(tag, platform, variant)
    if git('-C', 'original', 'rev-parse', 'HEAD') != SOURCES[tag]:
        raise ValueError('Original source changed')
    if git('-C', 'original', 'status', '--porcelain'):
        raise ValueError('Original source is dirty')
    files = list(Path('historical-install').rglob('*' + Path(name).suffix))
    if len(files) != 1:
        raise ValueError(f'Expected exactly one native library: {files}')
    data = files[0].read_bytes()
    if (platform == 'windows-2022' and not data.startswith(b'MZ')) or (platform == 'ubuntu-22.04' and not data.startswith(b'\x7fELF')):
        raise ValueError('Wrong native binary type')
    out = Path('historical-artifact')
    out.mkdir()
    shutil.copyfile(files[0], out / name)
    record = {'tag': tag, 'upstream_repository': 'ArduPilot/plotjuggler-apbin-plugins',
              'upstream_source': SOURCES[tag], 'product_source': SOURCES[tag],
              'build_tooling_source': git('rev-parse', 'HEAD'),
              'source_modifications': [], 'platform': platform, 'variant': variant,
              'host': 'PlotJuggler 3.9.2', 'qt': '5.15.2' if platform == 'windows-2022' else 'Ubuntu 22.04 Qt5 packages',
              'build_flags': ['-include array', '-include cstring'] if platform == 'ubuntu-22.04' else [],
              'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'filename': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'validation': 'Qt DataLoader dynamic loading, real BIN parsing, exact unit-label variant assertion'}
    (out / 'SOURCE.json').write_text(json.dumps(record, indent=2) + '\n')
    shutil.copyfile('original/LICENSE', out / 'UPSTREAM-LICENSE')

if __name__ == '__main__':
    main(*sys.argv[1:])
