#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Promote exact tested CI artifacts; never rebuild or replace a public release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile

REPO = "reliable-ly0411/plotjuggler-apbin-plugins"
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-rc\.(?:0|[1-9][0-9]*))?")
ROOT = Path(__file__).resolve().parents[1]


def gh(*args, check=True):
    return subprocess.run(["gh", *map(str, args)], check=check, capture_output=True, text=True)


def api(path):
    return json.loads(gh("api", f"repos/{REPO}/{path}").stdout)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_config(root):
    config = json.loads((root / "release.json").read_text())
    version = config["version"]
    if not SEMVER.fullmatch(version) or (root / "VERSION").read_text().strip() != version:
        raise ValueError("VERSION and release.json must contain the same valid release version")
    if config["line"] == "main":
        if config["branch"] != "main" or "-" in version or config["prerelease"]:
            raise ValueError("main must be a stable release on main")
        if config["workflow"] != ".github/workflows/build.yml":
            raise ValueError("main must use the upstream build workflow")
    elif config["line"] == "sdk4":
        if config["branch"] != "plotjuggler-4.x-sdk" or not config["prerelease"] or "-rc." not in version:
            raise ValueError("SDK4 must remain a release candidate on its independent branch")
        manifest = json.loads((root / "sdk4/manifest.json").read_text())
        if manifest.get("license") != "LGPL-3.0-only":
            raise ValueError("SDK manifest must retain the reviewed upstream LGPLv3 scope")
        if manifest["version"] != version:
            raise ValueError("SDK embedded manifest and release versions differ")
        if manifest["min_sdk_required"] != "0.34.1" or manifest["suggested_sdk_version"] != "0.34.1":
            raise ValueError("SDK ABI is not the reviewed 0.34.1 release boundary")
        if config["workflow"] != ".github/workflows/sdk4.yml":
            raise ValueError("SDK4 must use its native SDK workflow")
    else:
        raise ValueError("Unknown release line")
    body = (root / config["notes"]).read_text()
    upstream = (root / "docs/releases/upstream-v1.1.0.md").read_text().strip()
    if upstream not in body or config["title"].find("v" + version) < 0:
        raise ValueError("Release title/version or complete upstream notes are missing")
    return config


def expected_assets(config):
    if config["line"] == "main":
        return {f"{'lib' if platform == 'ubuntu-22.04' else ''}DataAPBin_{variant}.{ext}"
                for platform, ext in [("ubuntu-22.04", "so"), ("windows-2022", "dll")]
                for variant in ["no_units", "with_units", "with_units_rcou"]}
    return {f"ardupilot_source_plugin-v{config['version']}-sdk0.34.1-{platform}-x86_64.zip"
            for platform in ["linux-ubuntu22.04", "windows"]}


def collect(config, downloads, assets):
    assets.mkdir()
    if config["line"] == "main":
        for platform, ext in [("ubuntu-22.04", "so"), ("windows-2022", "dll")]:
            for key, variant in [("plain", "no_units"), ("units", "with_units"), ("units-rcou", "with_units_rcou")]:
                files = list((downloads / f"DataAPBin-{platform}-{key}").rglob(f"*.{ext}"))
                if len(files) != 1:
                    raise ValueError(f"Expected exactly one {platform}/{key} tested library, found {files}")
                name = f"{'lib' if ext == 'so' else ''}DataAPBin_{variant}.{ext}"
                shutil.copyfile(files[0], assets / name)
    else:
        for name in expected_assets(config):
            files = list(downloads.rglob(name))
            if len(files) != 1:
                raise ValueError(f"Expected exactly one final SDK package: {name}")
            with zipfile.ZipFile(files[0]) as archive:
                manifests = [p for p in archive.namelist() if p.endswith('.pjmanifest.json')]
                if len(manifests) != 1:
                    raise ValueError("SDK package has no unique manifest sidecar")
                manifest = json.loads(archive.read(manifests[0]))
                if manifest.get('license') != 'LGPL-3.0-only':
                    raise ValueError('Packaged manifest does not match the reviewed LGPLv3 scope')
                if manifest['version'] != config['version']:
                    raise ValueError("Packaged manifest does not match release version")
            shutil.copyfile(files[0], assets / name)
    if {p.name for p in assets.iterdir()} != expected_assets(config):
        raise ValueError("Unexpected release attachment set")
    hashes = {p.name: digest(p) for p in sorted(assets.iterdir())}
    (assets / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in hashes.items()))
    return hashes


def publish(run_id, source_sha):
    if os.environ.get("GITHUB_REPOSITORY") != REPO or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Run only in the intended repository with a full source SHA")
    config = validate_config(ROOT)
    checked_out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if checked_out != source_sha:
        raise ValueError("Checkout differs from approved source commit")
    run = api(f"actions/runs/{run_id}")
    expected = {"head_sha": source_sha, "head_branch": config['branch'], "path": config['workflow'],
                "status": "completed", "conclusion": "success", "event": "push"}
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError(f"Candidate run {key}: expected {value}, got {run.get(key)}")
    if run['repository']['full_name'] != REPO:
        raise ValueError("Candidate belongs to another repository")
    if api(f"git/ref/heads/{config['branch']}")['object']['sha'] != source_sha:
        raise ValueError("Release branch moved; review the new commit before publishing")
    prior_tags = {r['ref']: r['object']['sha'] for r in api('git/matching-refs/tags/')}
    tag = "v" + config['version']
    if gh("api", f"repos/{REPO}/git/ref/tags/{tag}", check=False).returncode == 0:
        raise ValueError("Tag already exists; public version anchors are never reused")
    if gh("release", "view", tag, "--repo", REPO, check=False).returncode == 0:
        raise ValueError("Release already exists; no overwrite or clobber is permitted")
    jobs = api(f"actions/runs/{run_id}/jobs?per_page=100")
    if jobs['total_count'] > 100 or any(j['conclusion'] not in ('success', 'skipped') for j in jobs['jobs']):
        raise ValueError("Candidate job evidence is incomplete or not successful")
    expected_jobs = 6 if config['line'] == 'main' else 2
    completed_plugins = [j for j in jobs['jobs'] if j['conclusion'] == 'success' and
                         (j['name'].startswith(('plain (', 'units (', 'units-rcou (')) if config['line'] == 'main'
                          else j['name'].startswith('plugin ('))]
    if len(completed_plugins) != expected_jobs:
        raise ValueError("Not all target-platform plugin jobs passed")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        downloads = tmp / 'downloads'
        gh('run', 'download', run_id, '--repo', REPO, '--dir', downloads)
        assets = tmp / 'assets'
        hashes = collect(config, downloads, assets)
        notes = (ROOT / config['notes']).read_text().rstrip() + '\n\n## Exact build and verification\n\n'
        workflow_sha = os.environ.get('GITHUB_WORKFLOW_SHA', 'unknown')
        notes += f"- Source/tag commit: [`{source_sha}`](https://github.com/{REPO}/commit/{source_sha}).\n"
        notes += f"- Candidate build and native smoke tests: [{run_id}]({run['html_url']}). The attached bytes are promoted from this run without rebuilding.\n"
        notes += f"- Publication workflow commit: `{workflow_sha}`.\n- SHA-256 (also in `SHA256SUMS`):\n\n"
        notes += '\n'.join(f"  - `{name}` ({(assets / name).stat().st_size} bytes): `{value}`" for name, value in hashes.items()) + '\n'
        notes_path = tmp / 'notes.md'
        notes_path.write_text(notes)
        files = list(sorted(assets.iterdir()))
        gh('release', 'create', tag, '--repo', REPO, '--target', source_sha, '--draft',
           '--title', config['title'], '--notes-file', notes_path, *files)
        gh('release', 'edit', tag, '--repo', REPO, '--draft=false',
           '--prerelease=' + str(config['prerelease']).lower(),
           '--latest=' + str(not config['prerelease']).lower())
        release = api(f'releases/tags/{tag}')
        if release['draft'] or release['prerelease'] != config['prerelease']:
            raise ValueError('Published release classification is incorrect')
        if {a['name'] for a in release['assets']} != {p.name for p in files}:
            raise ValueError('Public attachment set differs from the verified candidate')
        tag_object = api(f'git/ref/tags/{tag}')['object']
        while tag_object['type'] == 'tag':
            tag_object = api(f"git/tags/{tag_object['sha']}")['object']
        if tag_object['type'] != 'commit' or tag_object['sha'] != source_sha:
            raise ValueError('Published tag does not resolve to the tested source commit')
        after_tags = {r['ref']: r['object']['sha'] for r in api('git/matching-refs/tags/')}
        if any(after_tags.get(ref) != sha for ref, sha in prior_tags.items()):
            raise ValueError('An existing tag changed during publication')
        readback = tmp / 'readback'
        readback.mkdir()
        for asset in release['assets']:
            dest = readback / asset['name']
            # Public browser download URLs: no authorization header, token or cookies.
            for attempt in range(8):
                try:
                    urllib.request.urlretrieve(asset['browser_download_url'], dest)
                    break
                except Exception:
                    if attempt == 7:
                        raise
                    time.sleep(5)
            original = assets / asset['name']
            if dest.stat().st_size != original.stat().st_size or digest(dest) != digest(original):
                raise ValueError('Public download differs: ' + asset['name'])
        latest = api('releases/latest')
        if config['prerelease'] and latest['tag_name'] == tag:
            raise ValueError('SDK prerelease incorrectly replaced Latest')
        if not config['prerelease'] and latest['tag_name'] != tag:
            raise ValueError('Stable release did not become Latest')
        proof = {'release': release['html_url'], 'tag': tag, 'source_sha': source_sha,
                 'candidate_run': int(run_id), 'publication_workflow_sha': workflow_sha,
                 'latest': latest['tag_name'], 'public_download_verified': True, 'previous_tags_unchanged': True,
                 'assets': [{'name': p.name, 'size': p.stat().st_size, 'sha256': digest(p)} for p in files]}
        (ROOT / 'public-download-verification.json').write_text(json.dumps(proof, indent=2) + '\n')
        print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-run', required=True, type=int)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    publish(args.candidate_run, args.source_sha)
