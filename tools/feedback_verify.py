"""Capture dated test evidence without claiming passes from missing/skipped tests.

python -m tools.feedback_verify --out-root runs/feedback/verification
"""
import argparse
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.common.config import ROOT, save_json


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.out_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    commands = ([sys.executable, '-m', 'pip', 'freeze'], ['git', 'rev-parse', 'HEAD'],
                ['git', 'status', '--short'], [sys.executable, '-m', 'pytest', '-q', '-ra',
                                             f'--junitxml={root / "pytest.xml"}'])
    records = []
    for index, command in enumerate(commands):
        log_path = root / f'{index}.log'
        with log_path.open('w', encoding='utf-8') as log:
            try:
                result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                code = result.returncode
            except OSError as error:
                log.write(str(error))
                code = -1
        records.append(dict(command=command, exit_code=code, log=log_path.name))
    save_json(dict(date=datetime.now(timezone.utc).isoformat(), python=sys.version,
                   executable=sys.executable, platform=platform.platform(), commands=records,
                   limitation='Python portable/dispatcher parity is not measured browser/device performance'),
              root / 'verification.json')
    raise SystemExit(0 if all(r['exit_code'] == 0 for r in records) else 1)


if __name__ == '__main__':
    main()
