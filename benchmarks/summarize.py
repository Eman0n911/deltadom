"""Summarize immutable capture rows; no score or cost inference."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    rows=[json.loads(line) for line in (args.run/'rows.jsonl').read_text().splitlines()]
    groups=defaultdict(list)
    blocks=defaultdict(list)
    for row in rows:
        scope='local-shop' if row['case']=='local-shop' else 'MiniWoB-derived'
        groups[(scope,row['arm'])].append(row)
        blocks[(scope,row['arm'],row['seed'])].append(row)
    def aggregate(rs):
        valid=[r for r in rs if r['status']=='ok']
        return {'calls':len(rs),'errors':len(rs)-len(valid),
                'tokens':sum(r['tokens'] for r in valid),'bytes':sum(r['bytes'] for r in valid),
                'wall_p50_ms':round(statistics.median(r['wall_ms'] for r in valid),3),
                'page_mutations':sum(not r['page_unchanged'] for r in rs)}
    summary={'groups':[dict(scope=k[0],arm=k[1],**aggregate(v)) for k,v in sorted(groups.items())],
             'blocks':[dict(scope=k[0],arm=k[1],seed=k[2],**aggregate(v)) for k,v in sorted(blocks.items())],
             'delta_reconstruction_checks':sum(r.get('reconstruction_equal',False) for r in rows),
             'unactionable_script_targets':[dict(seed=r['seed'],case=r['case'],step=r['step'],arm=r['arm'],**r['next_script_target'])
                                           for r in rows if r.get('next_script_target') and not r['next_script_target']['interactive']]}
    (args.run/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    lines=['| Scope | Arm | Captures | Tokens | Call p50 ms | Errors |','|---|---|---:|---:|---:|---:|']
    for row in summary['groups']:
        lines.append(f"| {row['scope']} | {row['arm']} | {row['calls']} | {row['tokens']:,} | {row['wall_p50_ms']:.2f} | {row['errors']} |")
    text='\n'.join(lines)+'\n'
    (args.run/'table.md').write_text(text)
    print(text)


if __name__=='__main__': main()
