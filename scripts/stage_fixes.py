from pathlib import Path
import shutil
import subprocess
import sys


def main(files: list[str]) -> int:
    if not files:
        return 0

    existing = [f for f in files if Path(f).exists()]
    if not existing:
        return 0

    git = shutil.which("git")
    if git is None:
        return 1

    subprocess.run([git, "add", "--", *existing], check=True)  # noqa: S603
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
