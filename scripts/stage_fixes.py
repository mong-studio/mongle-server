from pathlib import Path
import subprocess
import sys

def main(files: list[str]) -> int:
  if not files:
    return 0
  
  existing = [f for f in files if Path(f).exists()]
  if not existing:
    return 0
  
  subprocess.run(["git", "add", "--", *existing], check=True)
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
  