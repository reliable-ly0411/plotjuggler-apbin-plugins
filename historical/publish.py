#!/usr/bin/env python3
"""Publish verified original-tag artifacts without changing tags or Latest."""
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
from package import SOURCES, asset_name

REPO='reliable-ly0411/plotjuggler-apbin-plugins'
UPSTREAM='ArduPilot/plotjuggler-apbin-plugins'
ROOT=Path(__file__).resolve().parent

def gh(*args, check=True):
    return subprocess.run(['gh',*map(str,args)],check=check,capture_output=True,text=True)
def api(path, repo=REPO):
    return json.loads(gh('api',f'repos/{repo}/{path}').stdout)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def matrix(tag):
    return [('ubuntu-22.04','no_units'),('ubuntu-22.04','with_units')] + ([('windows-2022','no_units')] if tag=='v1.1.0' else [])
def commit_for_tag(tag, repo):
    obj=api(f'git/ref/tags/{tag}',repo)['object']
    while obj['type']=='tag': obj=api(f"git/tags/{obj['sha']}",repo)['object']
    if obj['type']!='commit': raise ValueError('Tag is not a commit')
    return obj['sha']

def collect(tag, downloads, out, run):
    out.mkdir()
    records=[]
    for platform,variant in matrix(tag):
        src=downloads/f'historical-{tag}-{platform}-{variant}'
        rec=json.loads((src/'SOURCE.json').read_text())
        expected={'tag':tag,'upstream_repository':UPSTREAM,'upstream_source':SOURCES[tag],
                  'product_source':SOURCES[tag],'build_tooling_source':run['head_sha'],'source_modifications':[],
                  'platform':platform,'variant':variant,'run_id':str(run['id']),'run_attempt':str(run['run_attempt']),
                  'filename':asset_name(tag,platform,variant),'host':'PlotJuggler 3.9.2',
                  'host_source':{'repository':'PlotJuggler/PlotJuggler','tag':'3.9.2','commit':'d115b540c4f2664259a594259b9e11595f0263fc'}}
        for k,v in expected.items():
            if rec.get(k)!=v: raise ValueError(f'Provenance mismatch: {k}')
        lib=src/rec['filename']
        if lib.stat().st_size!=rec['size'] or digest(lib)!=rec['sha256']: raise ValueError('Binary bytes differ')
        shutil.copyfile(lib,out/lib.name)
        records.append(rec)
    license_file=Path(__file__).parents[1]/'docs/releases/README-licenses.txt'
    full_text=license_file.read_text()
    legal=full_text[full_text.index('==================== GNU LGPL VERSION 3'):]
    readme=f'''ArduPilot BIN {tag} — original upstream source rebuild

Install exactly one variant in a compatible PlotJuggler 3.9.2 plugin directory.
Verify SHA256SUMS and restart the host after changing plugin paths.
These downloads contain only native plugin libraries, not a standalone viewer.
Linux: Ubuntu 22.04 x86-64 / Qt5. Windows: x86-64 / MSVC / Qt5.15.2.
No compatibility with other host versions, macOS, ARM, or the PJ4 SDK is claimed.

Original upstream source and identical fork tag:
https://github.com/{UPSTREAM}/tree/{SOURCES[tag]}
https://github.com/{REPO}/tree/{tag}
Build tooling:
https://github.com/{REPO}/tree/{run['head_sha']}
Host base source: https://github.com/PlotJuggler/PlotJuggler/tree/d115b540c4f2664259a594259b9e11595f0263fc

No product-source files are modified. Linux compile flags explicitly supply
<array> and <cstring> standard headers omitted by historical source; this is a
build compatibility measure, not a backport of current parser changes.
These are reproducible-source rebuilds, not copies of upstream binary assets.
All runtime limitations and fixes missing from these historical releases remain.

The plugin is LGPLv3; original attribution includes Pierre Kancir and Jonas
Withelm (IAV GmbH). Source files retain their full original attribution.
The plugin remains separately replaceable; debugging modifications is permitted.
PlotJuggler base code is MPL-2.0. Full license texts follow the provenance.

Exact per-binary provenance:
{json.dumps(records,ensure_ascii=False,indent=2)}

'''
    (out/'README-licenses.txt').write_text(readme+legal)
    hashes={p.name:digest(p) for p in sorted(out.iterdir())}
    (out/'SHA256SUMS').write_text(''.join(f'{sha}  {name}\n' for name,sha in hashes.items()))
    return hashes

def publish(run_id,tooling_sha,tag):
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or tag not in SOURCES or not re.fullmatch('[0-9a-f]{40}',tooling_sha):
        raise ValueError('Invalid repository, tag, or build source')
    run=api(f'actions/runs/{run_id}')
    for key,value in {'head_sha':tooling_sha,'head_branch':'main','path':'.github/workflows/upstream-tags.yml','status':'completed','conclusion':'success','event':'workflow_dispatch'}.items():
        if run.get(key)!=value: raise ValueError(f'Candidate mismatch: {key}')
    if run['repository']['full_name']!=REPO: raise ValueError('Wrong candidate repository')
    jobs=api(f'actions/runs/{run_id}/jobs?per_page=100')
    expected_jobs={'PlotJuggler (ubuntu-22.04)', 'PlotJuggler (windows-2022)'} | {f'{t} {plat} {var}' for t in SOURCES for plat,var in matrix(t)}
    if jobs['total_count']!=7 or len(jobs['jobs'])!=7 or {j['name'] for j in jobs['jobs']}!=expected_jobs or any(j['conclusion']!='success' for j in jobs['jobs']):
        raise ValueError('Incomplete seven-job build matrix')
    if commit_for_tag(tag,UPSTREAM)!=SOURCES[tag] or commit_for_tag(tag,REPO)!=SOURCES[tag]: raise ValueError('Upstream/fork tags do not match')
    releases=api('releases?per_page=100')
    if any(r['tag_name']==tag for r in releases): raise ValueError('Existing release must not be overwritten')
    if api('releases/latest')['tag_name']!='v1.2.0': raise ValueError('Unexpected current Latest')
    upstream=api(f'releases/tags/{tag}',UPSTREAM)
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        gh('run','download',run_id,'--repo',REPO,'--dir',tmp/'downloads')
        assets=tmp/'assets'
        hashes=collect(tag,tmp/'downloads',assets,run)
        body=f'''## 来源与版本

这是上游 `{tag}` 原始源码的重新构建，源码提交 `{SOURCES[tag]}`。与上游标签逐一核对一致，不含本仓 v1.2.0 的后续上游 main 改动，也不含 PlotJuggler 4.x SDK 适配。原标签未移动。

## 上游发布说明（全文）

来源：{upstream['html_url']}

{upstream['body']}

## 下载与使用

沿用对应上游的二进制清单与文件名。选择一个单位标注变体，放入兼容的 PlotJuggler 插件搜索目录并重启。先核对 SHA256SUMS。README-licenses.txt 提供完整许可证、安装说明与逐文件溯源。

测试宿主：PlotJuggler 3.9.2 / Qt5；Linux 为 Ubuntu 22.04 x86-64，Windows 为 MSVC / Qt5.15.2 x86-64。不包含查看器；未声明其他宿主/Qt版本、macOS、ARM或PJ4兼容。

## 构建与验证

- 产品源码：`{SOURCES[tag]}`，源码文件未修改。
- 构建工具提交：`{tooling_sha}`。
- 原包构建及动态加载/真实BIN/单位标注验证：{run['html_url']}，attempt {run['run_attempt']}。
- Linux 编译显式补入历史代码遗漏的标准头 array/cstring；未回移新解析功能。
- 直接提升上述已验原始库，不在发布时重建；这是源码复建，不是上游附件镜像或字节相同声明。
- 历史代码仍有后续版本已经修复的限制，推荐日常使用当前 v1.2.0；本发布不改变 Latest。

## SHA256

'''+''.join(f'- `{name}` ({(assets/name).stat().st_size} bytes): `{sha}`\n' for name,sha in hashes.items())
        notes=tmp/'notes.md';notes.write_text(body)
        gh('release','create',tag,'--repo',REPO,'--verify-tag','--draft','--title',f'ArduPilot BIN {tag} · 上游标签复建','--notes-file',notes,*sorted(assets.iterdir()))
        gh('release','edit',tag,'--repo',REPO,'--draft=false','--prerelease=false','--latest=false')
        release=api(f'releases/tags/{tag}')
        if release['draft'] or release['prerelease'] or {a['name'] for a in release['assets']}!={p.name for p in assets.iterdir()}:raise ValueError('Published metadata mismatch')
        for a in release['assets']:
            dest=tmp/a['name']
            for attempt in range(8):
                try:urllib.request.urlretrieve(a['browser_download_url'],dest);break
                except Exception:
                    if attempt==7:raise
                    time.sleep(5)
            if dest.stat().st_size!=(assets/a['name']).stat().st_size or digest(dest)!=digest(assets/a['name']):raise ValueError('Public download differs')
        if commit_for_tag(tag,REPO)!=SOURCES[tag] or api('releases/latest')['tag_name']!='v1.2.0':raise ValueError('Tag or Latest changed')
        proof={'release':release['html_url'],'source':SOURCES[tag],'build_tooling':tooling_sha,'candidate_run':run_id,'attempt':run['run_attempt'],'public_download_verified':True,'latest':'v1.2.0','assets':[{ 'name':p.name,'size':p.stat().st_size,'sha256':digest(p)} for p in sorted(assets.iterdir())]}
        (Path.cwd()/f'historical-{tag}-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
        print(json.dumps(proof,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate-run',type=int,required=True);p.add_argument('--tooling-sha',required=True);p.add_argument('--tag',choices=SOURCES,required=True)
    a=p.parse_args();publish(a.candidate_run,a.tooling_sha,a.tag)
