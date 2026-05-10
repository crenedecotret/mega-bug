"""Build script — trigger PyInstaller for cross-platform packaging."""
import sys
import subprocess


def build() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "MegaBugModern",
        "--add-data", "src:src",
        "src/main.py",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    build()
