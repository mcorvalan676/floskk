import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT_DIRECTORIES = (".venv", ".venv-workers")


def run_command(command):
    if os.name == "nt" and command[0].lower().endswith((".cmd", ".bat")):
        subprocess.run(subprocess.list2cmdline(command), cwd=PROJECT_ROOT, check=True, shell=True)
    else:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy a Python Worker without packaging local Python environments."
    )
    parser.add_argument("worker_name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the Worker without uploading it.",
    )
    args = parser.parse_args()

    uv = shutil.which("uv")
    uv_command = [uv] if uv else [sys.executable, "-m", "uv"]
    run_command([*uv_command, "run", "pywrangler", "sync"])

    temporary_root = Path(tempfile.mkdtemp(prefix="conectatalento-wrangler-"))
    moved_directories = []
    try:
        for directory_name in ENVIRONMENT_DIRECTORIES:
            source = PROJECT_ROOT / directory_name
            if source.exists():
                destination = temporary_root / directory_name
                shutil.move(str(source), str(destination))
                moved_directories.append((source, destination))

        npx = shutil.which("npx")
        if not npx:
            raise FileNotFoundError("Could not find npx; install Node.js before deploying.")
        command = [npx, "--yes", "wrangler", "deploy", "--name", args.worker_name]
        if args.dry_run:
            command.append("--dry-run")
        run_command(command)
    finally:
        restore_errors = []
        for source, destination in reversed(moved_directories):
            if not destination.exists():
                continue
            if source.exists():
                restore_errors.append(
                    f"Cannot restore {source}: the path was recreated during deployment."
                )
                continue
            shutil.move(str(destination), str(source))

        if not restore_errors:
            temporary_root.rmdir()
        if restore_errors:
            raise RuntimeError(" ".join(restore_errors))


if __name__ == "__main__":
    main()
