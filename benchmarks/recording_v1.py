"""Retrospective, same-information storage experiment. No model calls."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

from deltadom.tape import TapeWriter, read_tape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'deltadom-output/recording-benchmark'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUT)
    OUT = parser.parse_args().output
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []
    for corpus in ['observation-v2', 'holdout-v2']:
        for arm in ['browser-use', 'agent-browser-full', 'deltadom-full']:
            groups = {}
            for path in sorted((ROOT / 'artifacts/benchmarks' / corpus).glob('*-' + arm + '.txt')):
                name = path.name.removesuffix('-' + arm + '.txt')
                group, step = name.rsplit('-', 1)
                groups.setdefault(group, []).append((int(step), path))
            for group, files in sorted(groups.items()):
                files.sort()
                snapshots = [p.read_text() for _, p in files]
                name = f'{corpus}-{group}-{arm}'
                counts = {}
                for mode, interval in [('full', 1), ('adaptive', 20)]:
                    target = OUT / f'{name}-{mode}.ddt'
                    start = time.perf_counter()
                    with TapeWriter(target, checkpoint_interval=interval) as writer:
                        for text in snapshots:
                            writer.add(text)
                    elapsed = (time.perf_counter() - start) * 1000
                    start = time.perf_counter()
                    rebuilt = [entry.text for entry in read_tape(target)]
                    decode_ms = (time.perf_counter() - start) * 1000
                    assert rebuilt == snapshots
                    counts[mode] = {'bytes': target.stat().st_size, 'encode_ms': elapsed,
                                    'decode_ms': decode_ms, 'exact': True}
                offline = gzip.compress(json.dumps(snapshots, ensure_ascii=False,
                                                   separators=(',', ':')).encode(),
                                        compresslevel=6, mtime=0)
                assert json.loads(gzip.decompress(offline)) == snapshots
                (OUT / f'{name}.json.gz').write_bytes(offline)
                rows.append({'corpus': corpus, 'group': group, 'source': arm,
                             'snapshots': len(snapshots),
                             'raw_bytes': sum(len(s.encode()) for s in snapshots),
                             'inputs': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for _, p in files},
                             **counts, 'offline_gzip_bytes': len(offline)})
    summary = {}
    for row in rows:
        scope = 'shop' if 'local-shop' in row['group'] else row['corpus']
        key = scope + '/' + row['source']
        totals = summary.setdefault(key, dict(snapshots=0, raw=0, full=0, adaptive=0, offline_gzip=0))
        for k, v in dict(snapshots=row['snapshots'], raw=row['raw_bytes'],
                         full=row['full']['bytes'], adaptive=row['adaptive']['bytes'],
                         offline_gzip=row['offline_gzip_bytes']).items():
            totals[k] += v
    report = {'scope': 'retrospective storage only; zero model calls', 'zlib_level': 6,
              'sources': {p: sha((ROOT / p).read_bytes()) for p in
                          ['python/deltadom/tape.py', 'benchmarks/recording_v1.py',
                           'benchmarks/RECORDING-PROTOCOL.md']},
              'summary': summary, 'episodes': rows}
    (OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
