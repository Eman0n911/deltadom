import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from deltadom.demo import run


async def test_demo_writes_portable_results_without_tokenizer(tmp_path):
    output = tmp_path / "folder with spaces" / "演示.json"
    result = await run(os.environ.get("DELTADOM_CHANNEL", "auto"), output)
    assert result["steps"] == 8
    assert result["reconstruction_equal"]
    assert "tokenizer" not in result
    assert [o["frame"]["kind"] for o in result["observations"]] == ["full"] + ["delta"] * 6 + [
        "full"
    ]
    assert result["observations"][1]["frame"]["upsert"] == []
    assert result["observations"][3]["api"]
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert output.with_suffix(".png").read_bytes().startswith(b"\x89PNG")
    assert "Verified 8/8" in output.with_suffix(".txt").read_text(encoding="utf-8")
    recording = Path(result["recording"])
    first_bytes = recording.read_bytes()
    second = await run(os.environ.get("DELTADOM_CHANNEL", "auto"), output)
    assert second["recording"] != result["recording"]
    assert recording.read_bytes() == first_bytes
    assert second["recording_verification"]["snapshots"] == 8



@pytest.mark.parametrize("delay", ["-1", "nan", "inf"])
def test_cli_rejects_invalid_delay_before_opening_browser(delay):
    result = subprocess.run(
        [sys.executable, "-m", "deltadom.cli", "demo", "--delay", delay],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--delay" in result.stderr
    assert not result.stdout


def test_cli_reports_installed_version():
    from importlib.metadata import version
    result = subprocess.run([sys.executable, "-m", "deltadom.cli", "--version"],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == f"DeltaDOM {version('deltadom')}"
