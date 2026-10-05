"""Run every offline suite with the active Python environment and installed Node."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def commands(seed, coverage):
    node = shutil.which('node')
    if node is None:
        raise SystemExit('Node.js is required for frontend and game tests')
    backend = [sys.executable,'-m','pytest','-q',f'--test-order-seed={seed}',
               '--junitxml=artifacts/test-design-suite.xml']
    if coverage:
        backend += ['--cov=app','--cov-branch','--cov-report=xml:artifacts/coverage.xml',
                    '--cov-report=json:artifacts/coverage.json','--cov-report=term']
    yield 'Backend',backend,ROOT
    front = ROOT/'front'
    files = sorted([*front.glob('tests/*.test.mjs'),*front.glob('tests/*.test.ts')])
    yield 'Frontend',[node,'--experimental-strip-types','--test','--test-reporter=spec',
                      *map(str,files),str(ROOT/'tests/navigation.test.mjs')],front
    game = ROOT/'race-game'
    yield 'Race game',[node,'--test','--test-reporter=spec',*map(str,sorted(game.glob('tests/*.test.mjs')))],game
    yield 'Deployment contracts',[sys.executable,str(ROOT/'deploy/jenkins/test_deploy.py')],ROOT
    yield 'Boundary mutations',[node,str(ROOT/'scripts/check-test-mutations.mjs')],ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=20261005)
    parser.add_argument('--coverage',action='store_true')
    parser.add_argument('--list',action='store_true',help='Show commands without executing tests')
    args = parser.parse_args()
    (ROOT/'artifacts').mkdir(exist_ok=True)
    for label,command,cwd in commands(args.seed,args.coverage):
        print(f'\n{label}: {subprocess.list2cmdline(command)}',flush=True)
        if not args.list:
            result = subprocess.run(command,cwd=cwd,timeout=600)
            if result.returncode:
                return result.returncode
    return 0


if __name__=='__main__':
    raise SystemExit(main())
