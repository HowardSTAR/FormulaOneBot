"""Check bot, web, permissions and games in an isolated local test environment.

Uses the invoking Python environment and existing npm dependencies; never installs,
deploys, sends Telegram messages or connects to the production database.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    reports = ROOT / ".tmp/code-optimization"
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="f1hub-regression-") as directory:
        environment = {**os.environ, "BOT_TOKEN": "123456:TEST", "DATABASE_PATH": str(Path(directory) / "test.db"),
                       "ADMIN_EMAIL": "admin@example.test", "ADMIN_TELEGRAM_ID": "999001", "RUN_LIVE_PREDICTION_APIS": "0"}
        checks = [(ROOT, [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "--ignore=tests/test_prediction_api_sources_live.py", f"--junitxml={reports / 'regression.xml'}"])]
        if not args.backend_only:
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            node = shutil.which("node")
            compiler = ROOT / "front/node_modules/typescript/bin/tsc"
            if not npm or not node:
                raise SystemExit("npm is not available; activate Node.js or use --backend-only")
            if not compiler.is_file():
                raise SystemExit("Frontend dependencies are missing; install them before running the checks")
            checks += [(ROOT / "front", [npm, "run", "test:performance"]),
                       (ROOT / "front", [node, str(compiler), "--noEmit", "-p", "tsconfig.app.json"]),
                       (ROOT / "front", [npm, "run", "lint"]),
                       (ROOT / "race-game", [npm, "test"])]
            if not args.skip_build:
                checks += [(ROOT / "front", [npm, "run", "build"]), (ROOT / "front", [npm, "run", "check:budget"])]
        for cwd, command in checks:
            print(f"\nChecking {cwd.name}: {' '.join(command)}", flush=True)
            subprocess.run(command, cwd=cwd, env=environment, check=True)
    print("\nAll selected regression checks passed.")


if __name__ == "__main__":
    main()
