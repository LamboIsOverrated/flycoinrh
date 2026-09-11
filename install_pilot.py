"""Pinned Windows wheel installer with PyPI SHA-256 verification.

Used when pip's remote wheel/metadata download stalls. No source builds.
"""
import concurrent.futures
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

ROOT=Path(__file__).parent
CACHE=ROOT/'.garden'/'wheels'

def fetch(spec):
    name,version=spec.split('==')
    try:
        if importlib.metadata.version(name)==version:return None
    except importlib.metadata.PackageNotFoundError:pass
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:
        metadata=json.load(response)
    supported=set(sys_tags())
    wheels=[x for x in metadata['urls'] if x['filename'].endswith('.whl') and parse_wheel_filename(x['filename'])[3] & supported]
    wheels.sort(key=lambda x:('none-any' not in x['filename'],x['filename']))
    if not wheels:raise RuntimeError(f'No compatible wheel: {spec}')
    item=wheels[0];path=CACHE/item['filename']
    if not path.exists():
        with urllib.request.urlopen(item['url'],timeout=60) as response:
            data=response.read()
        if hashlib.sha256(data).hexdigest()!=item['digests']['sha256']:raise RuntimeError('Wheel checksum mismatch')
        path.write_bytes(data)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['digests']['sha256']:raise RuntimeError('Cached wheel checksum mismatch')
    print(f'Verified {spec}',flush=True)
    return str(path)

if __name__=='__main__':
    CACHE.mkdir(parents=True,exist_ok=True)
    specs=[s.strip() for s in (ROOT/'requirements-pilot.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        files=[p for p in pool.map(fetch,specs) if p]
    if files:subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps',*files],check=True)
    subprocess.run([sys.executable,'-m','pip','check'],check=True)
