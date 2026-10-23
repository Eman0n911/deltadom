"""Prepare a fresh public tree; preserve local raw evidence and Git history.

Only allowlisted project files are exported. Text logs/reports have workstation
paths replaced; compressed actual-agent message recordings stay local. This is
not a general secret scanner: inspect the resulting file list before publishing.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    ".gitignore",
    ".gitattributes",
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "requirements-dev.lock",
    "README.md",
    "README.en.md",
    "README.ja.md",
    "README.fr.md",
    "START_HERE.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "install.py",
    "run.py",
    "Start DeltaDOM.command",
}
FOLDERS = {
    ".github",
    "src",
    "python",
    "tests",
    "examples",
    "scripts",
    "docs",
    "benchmarks",
    "artifacts",
}
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".log",
    ".json",
    ".jsonl",
    ".py",
    ".rs",
    ".html",
    ".js",
    ".yml",
    ".toml",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    candidates = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    paths, redacted, omitted = [], [], []
    for name in sorted(set(candidates) - {""}):
        rel = Path(name)
        if name not in ROOT_FILES and rel.parts[0] not in FOLDERS:
            continue
        if name == "artifacts/benchmarks/native-agent-contract/agent.ddt":
            omitted.append(name)
            continue
        source = ROOT / rel
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"unsupported publication file: {name}")
        data = source.read_bytes()
        if source.suffix in TEXT_SUFFIXES:
            text = data.decode("utf-8")
            clean = text.replace(str(Path.home()), "/HOME")
            clean = re.sub(r"(?:/private)?/TMP/\s]+/[^/\s]+/", "/TMP/", clean)
            if clean != text:
                redacted.append(name)
            data = clean.encode("utf-8")
        target = out / rel
        if rel.parts[:2] == (".github", "workflows"):
            target = out / "ci" / rel.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(source.stat().st_mode & 0o777)
        paths.append(name)
    # Historical core sources allow reproducing the 0.3 measurements without
    # publishing the development branch/history or a workstation environment.
    evidence = out / "evidence"
    evidence.mkdir()
    target_source = evidence / "source-0.3.0.tar.gz"
    if (ROOT / "evidence/source-0.3.0.tar.gz").exists():
        target_source.write_bytes((ROOT / "evidence/source-0.3.0.tar.gz").read_bytes())
    else:
        subprocess.run(
            [
                "git",
                "archive",
                "--format=tar.gz",
                "--output=" + str(target_source),
                "69cc2cb",
                "src",
                "python",
                "Cargo.toml",
                "Cargo.lock",
                "pyproject.toml",
                "requirements-dev.lock",
            ],
            cwd=ROOT,
            check=True,
        )
    report = {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip(),
        "files": len(paths),
        "ci": "Workflow retained as inactive ci/check.yml; publishing token lacks workflow scope",
        "path_redactions": redacted,
        "omitted": omitted,
        "note": "Public text logs are path-redacted derivatives; local originals retained. "
        "Captured synthetic observation text and codec/source bindings are unchanged. "
        "No old Git history, environments, credentials or everyday browser profiles exported.",
    }
    (out / "PUBLIC_EXPORT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(out),
                "files": len(paths),
                "ci": "Workflow retained as inactive ci/check.yml; publishing token lacks workflow scope",
                "redacted": len(redacted),
                "omitted": omitted,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
