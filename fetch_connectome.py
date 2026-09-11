"""Download the upstream FlyEM inputs; never execute downloaded code."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
BASE = 'https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/'
FILES = {
    'body-annotations.feather': 'body-annotations-male-cns-v1.0-minconf-0.5.feather',
    'body-neurotransmitters.feather': 'body-neurotransmitters-male-cns-v1.0.feather',
    'connectome-weights.feather': 'connectome-weights-male-cns-v1.0-minconf-0.5.feather',
}

def main():
    target = ROOT / 'data'
    target.mkdir(exist_ok=True)
    manifest = {}
    for local, remote in FILES.items():
        path = target / local
        if not path.exists():
            temp = path.with_suffix('.partial')
            with urllib.request.urlopen(BASE + remote, timeout=90) as response, temp.open('wb') as output:
                expected = int(response.headers.get('Content-Length', 0))
                total = 0
                while chunk := response.read(4 * 1024 * 1024):
                    output.write(chunk)
                    total += len(chunk)
                if expected and total != expected:
                    raise RuntimeError(f'Incomplete download: {local}')
            temp.replace(path)
        digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
        manifest[local] = {'source': BASE + remote, 'bytes': path.stat().st_size, 'sha256': digest}
        print(f'{local}: {path.stat().st_size:,} bytes ready', flush=True)
    (target / 'sources.json').write_text(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
