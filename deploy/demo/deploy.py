"""Publish the public demo to Google Cloud Run, in Paris (DECISIONS.md, decision 32).

    gcloud auth login                          # once
    gcloud config set project PROJECT_ID       # a project with billing turned on
    python deploy/demo/deploy.py               # [--service NAME], default "feedforward-demo"

Turns on the Cloud Run and Cloud Build services, uploads what git tracks under
backend/ (tests left out) with the licences and this folder's Dockerfile, lets
Cloud Build make the image, and runs it as one instance that stops when nobody
uses it. Prints the demo's address. Each deploy starts a fresh instance, which
wipes the demo's accounts (its database lives inside the instance).
"""
from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REGION = "europe-west9"                          # Paris


def deploy_args(service: str, source: str, secret: str) -> list[str]:
    """The `gcloud run deploy` call. One instance at most: the database lives inside it, so a second instance
    would not know the first one's visitors. None when idle: the first visit after a pause waits for the start."""
    return ["run", "deploy", service, "--source", source, "--region", REGION, "--allow-unauthenticated",
            "--memory", "1Gi", "--cpu", "1", "--min-instances", "0", "--max-instances", "1",
            "--timeout", "120", "--set-env-vars", f"FEEDFORWARD_SECRET={secret}", "--quiet"]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def tracked() -> list[str]:
    """The files the image needs: the app as git has it, without its tests, and the licences."""
    files = _git("ls-files", "backend", "LICENSE", "DATA_LICENSES.md").splitlines()
    return [f for f in files if f and not f.startswith("backend/tests/")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--service", default="feedforward-demo", help="the Cloud Run service's name")
    args = parser.parse_args()
    gcloud = shutil.which("gcloud")
    if not gcloud:
        sys.exit("The gcloud tool is not installed: https://cloud.google.com/sdk/docs/install")

    def run(*a: str, capture: bool = False) -> str:
        done = subprocess.run([gcloud, *a], check=True, text=True, capture_output=capture)
        return (done.stdout or "").strip()

    project = run("config", "get-value", "project", capture=True)
    if not project:
        sys.exit("No project: gcloud config set project PROJECT_ID")
    print(f"Project {project}, region {REGION}")
    run("services", "enable", "run.googleapis.com", "cloudbuild.googleapis.com", "artifactregistry.googleapis.com")

    if _git("status", "--porcelain", "backend").strip():
        print("Note: backend/ has uncommitted changes; they are uploaded as they are on disk.")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for f in tracked():
            (stage / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, stage / f)
        shutil.copy2(HERE / "Dockerfile", stage / "Dockerfile")
        run(*deploy_args(args.service, str(stage), secrets.token_urlsafe(48)))

    url = run("run", "services", "describe", args.service, "--region", REGION, "--format", "value(status.url)", capture=True)
    print(f"Demo: {url}/app")


if __name__ == "__main__":
    main()
