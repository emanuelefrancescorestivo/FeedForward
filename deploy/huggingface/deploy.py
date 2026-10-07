"""Publish the public demo to a Hugging Face Space.

    hf auth login                              # once, with a token that can write
    python deploy/huggingface/deploy.py        # [--space NAME], default "feedforward"

Creates the Space (Docker) if it does not exist, gives it a fresh
FEEDFORWARD_SECRET, uploads what git tracks under backend/ (tests left out)
with the licences, this folder's Dockerfile and README.md (the Space card),
and prints the demo's address. Each upload rebuilds the Space, which wipes the
demo's accounts (its database lives inside the container).
"""
from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def tracked() -> list[str]:
    """The files the Space needs: the app as git has it, without its tests, and the licences."""
    files = _git("ls-files", "backend", "LICENSE", "DATA_LICENSES.md").splitlines()
    return [f for f in files if f and not f.startswith("backend/tests/")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--space", default="feedforward", help="the Space's name under your account")
    args = parser.parse_args()

    api = HfApi()
    user = api.whoami()["name"]
    repo = f"{user}/{args.space}"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
    api.add_space_secret(repo, "FEEDFORWARD_SECRET", secrets.token_urlsafe(48), description="Signs the demo's sign-in tokens")

    if _git("status", "--porcelain", "backend").strip():
        print("Note: backend/ has uncommitted changes; they are uploaded as they are on disk.")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for f in tracked():
            (stage / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, stage / f)
        for f in ("Dockerfile", "README.md"):
            shutil.copy2(HERE / f, stage / f)
        commit = _git("rev-parse", "--short", "HEAD").strip()
        api.upload_folder(folder_path=stage, repo_id=repo, repo_type="space",
                          commit_message=f"Demo from FeedForward {commit}", delete_patterns=["*", "**/*"])

    host = "".join(c if c.isalnum() else "-" for c in f"{user}-{args.space}".lower())
    print(f"Space: https://huggingface.co/spaces/{repo}")
    print(f"Demo:  https://{host}.hf.space/app  (ready when the build finishes, a few minutes)")


if __name__ == "__main__":
    main()
