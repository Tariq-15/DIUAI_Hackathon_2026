"""Reproducible feedback studies, isolated from the seed-42 reference.

python -m tools.feedback_evaluate --out-root runs/feedback
python -m tools.feedback_evaluate --out-root runs/feedback --run-seeds --seeds 42 43 44
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.common.config import load_config, save_json
from src.models.metrics import wilson_interval
from src.serve.recipient import check, default_costs


def recipient_matrix():
    """Fixed diagnostic set; never used to fit costs or suggestion thresholds.

    Covers familiar/unfamiliar intentions, swaps, neighbouring key slips,
    legitimate similar numbers and competing frequent contacts. A contact
    history is local to each case. Ordinary Levenshtein disables swaps.
    """
    rows = []
    ordinary = dict(sub={a: {b: float(a != b) for b in '0123456789'}
                         for a in '0123456789'}, transposition=2.)
    for number in ('01076254257', '01034567892', '01098765432'):
        slip = number[:-1] + ('8' if number[-1] != '8' else '5')
        swap = number[:-2] + number[-1] + number[-2]
        for familiar in (True, False):
            for similar in (True, False):
                numbers = {'known': number if familiar else '01011111111'}
                if similar:
                    numbers['competitor'] = number[:-2] + '00'
                history = {k: 8 for k in numbers}
                for kind, typed, intended in (('one_key', slip, number), ('swap', swap, number),
                                               ('legitimate_similar', slip, None),
                                               ('exact_contact', numbers['known'], None),
                                               ('distant', '01000000000', None)):
                    for model, costs in (('keypad', default_costs()), ('ordinary_edit', ordinary)):
                        suggestion = check(history, numbers, typed, costs)
                        target = suggestion['msisdn'] if suggestion else None
                        rows.append(dict(model=model, familiar=familiar, similar_contacts=similar,
                                         kind=kind, typed=typed, intended=intended, suggested=target,
                                         correct=target is not None and target == intended))
    groups = defaultdict(list)
    for row in rows:
        groups[(row['model'], row['familiar'], row['similar_contacts'], row['kind'])].append(row)
    summary = []
    for (model, familiar, similar, kind), group in groups.items():
        suggested = sum(r['suggested'] is not None for r in group)
        correct = sum(r['correct'] for r in group)
        eligible = sum(r['intended'] is not None for r in group)
        summary.append(dict(model=model, familiar=familiar, similar_contacts=similar, kind=kind,
                            n=len(group), suggestions=suggested, correct=correct,
                            false_suggestions=suggested-correct, no_suggestion=len(group)-suggested,
                            precision=correct/suggested if suggested else None,
                            recall=correct/eligible if eligible else None,
                            coverage=suggested/len(group), precision_ci=wilson_interval(correct, suggested)))
    return dict(status='synthetic diagnostic; not customer validation',
                baseline='unit-cost Levenshtein; same contact eligibility, ranking and 1.6 cutoff',
                limitations='Small fixed set; exact contacts can expose false suggestions. No threshold tuning.',
                rows=rows, summary=summary)


def aggregate_seed_metrics(runs):
    values = defaultdict(list)
    for seed, metrics in runs:
        fused = next(r for r in metrics['comparison'] if r['model'] == 'Prohori fused score')
        values['pr_auc'].append(fused['pr_auc'])
        for band, result in metrics['bands'].items():
            if band == 'band_counts':
                continue
            for metric in ('precision', 'recall', 'fpr'):
                values[f'{band}.{metric}'].append(result[metric])
        for row in metrics['per_scenario']:
            values[f"scenario.{row['scenario']}.recall_stepup"].append(row['recall_stepup'])
    return {key: dict(n=len(v), mean=sum(v)/len(v), minimum=min(v), maximum=max(v))
            for key, v in values.items()}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out-root', type=Path, required=True)
    parser.add_argument('--run-seeds', action='store_true')
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 43, 44])
    parser.add_argument('--scale', type=float, default=1.)
    parser.add_argument('--trials', type=int, default=0)
    args = parser.parse_args()
    root = args.out_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if len(set(args.seeds)) != len(args.seeds):
        parser.error('seeds must be distinct')
    save_json(recipient_matrix(), root / 'recipient_matrix.json')
    runs = []
    for seed in args.seeds if args.run_seeds else []:
        destination = root / f'seed-{seed}'
        if destination.exists():
            parser.error(f'refusing to overwrite existing seed run: {destination}')
        destination.mkdir()
        command = [sys.executable, '-m', 'src.pipeline', '--seed', str(seed), '--scale', str(args.scale),
                   '--trials', str(args.trials), '--out-root', str(destination), '--to', 'evaluate']
        with (destination / 'pipeline.log').open('w', encoding='utf-8') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        runs.append((seed, json.loads((destination / 'reports/metrics_test.json').read_text())))
    save_json(dict(date=datetime.now(timezone.utc).isoformat(), evidence='synthetic simulation',
                   split=load_config()['splits'], seeds=[s for s, _ in runs], scale=args.scale,
                   trials=args.trials, metrics=aggregate_seed_metrics(runs),
                   pending=['unseen fraud variants', 'amount-habit ablation', 'local-state cross-silo evaluation',
                            'customer validation', 'device and concurrency measurements']), root / 'summary.json')


if __name__ == '__main__':
    main()
