import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "canary-issues.sh"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None or shutil.which("jq") is None, reason="needs sh and jq")

STUB = """#!/bin/sh
printf '%s\\n' "$*" | tr '\\n' ' ' >> "$STUB_LOG"
printf '\\n' >> "$STUB_LOG"
case "$1 $2" in
  "issue list") cat "$STUB_ISSUES" ;;
  "label create") [ -z "${STUB_LABEL_ERROR:-}" ] || { echo "$STUB_LABEL_ERROR" >&2; exit 1; } ;;
esac
"""

FINDINGS = [
    {"key": "vimm:new-platform:Amiga", "title": "Vimm lists Amiga", "detail": "Add it."},
    {"key": "igir:update:v9.0.0", "title": "igir v9.0.0 is out", "detail": "Update."},
]


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(STUB)
        gh.chmod(0o755)
        self.log = tmp_path / "gh.log"
        self.log.write_text("")
        self.findings = tmp_path / "findings.json"
        self.issues = tmp_path / "issues.json"
        self.env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "STUB_LOG": str(self.log),
            "STUB_ISSUES": str(self.issues),
        }
        self.write(FINDINGS, [])

    def write(self, findings: list[dict[str, str]], issues: list[dict[str, object]]) -> None:
        self.findings.write_text(json.dumps(findings))
        self.issues.write_text(json.dumps(issues))

    def run(self, *args: str, path: str | None = None) -> subprocess.CompletedProcess[str]:
        assert SH is not None
        env = {**self.env, **({"PATH": path} if path is not None else {})}
        return subprocess.run(  # noqa: S603
            [SH, str(SCRIPT), *args, str(self.findings)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def commands(self) -> list[str]:
        return [line.strip() for line in self.log.read_text().splitlines()]


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_creates_an_issue_per_new_finding(harness: Harness) -> None:
    result = harness.run()
    assert result.returncode == 0, result.stderr
    commands = harness.commands()
    assert commands[0].startswith("label create canary --color ")
    assert commands[1] == "issue list --label canary --state open --limit 200 --json number,title"
    creates = [command for command in commands if command.startswith("issue create")]
    assert len(creates) == 2
    assert "--title canary: vimm:new-platform:Amiga" in creates[0]
    assert "--label canary" in creates[0]
    assert "Vimm lists Amiga  Add it.  The weekly canary found this." in creates[0]
    assert "--title canary: igir:update:v9.0.0" in creates[1]
    assert not [command for command in commands if command.startswith("issue close")]


def test_existing_issue_is_left_alone(harness: Harness) -> None:
    harness.write(FINDINGS, [{"number": 7, "title": "canary: vimm:new-platform:Amiga"}])
    assert harness.run().returncode == 0
    creates = [command for command in harness.commands() if command.startswith("issue create")]
    assert len(creates) == 1
    assert "igir:update:v9.0.0" in creates[0]


def test_resolved_issue_is_closed_with_a_comment(harness: Harness) -> None:
    harness.write(
        FINDINGS[:1],
        [
            {"number": 7, "title": "canary: vimm:new-platform:Amiga"},
            {"number": 9, "title": "canary: igir:update:v8.0.0"},
            {"number": 11, "title": "unrelated issue"},
        ],
    )
    assert harness.run().returncode == 0
    commands = harness.commands()
    closes = [command for command in commands if command.startswith("issue close")]
    assert closes == ["issue close 9 --comment The canary no longer reports this finding."]
    assert not [command for command in commands if command.startswith("issue create")]


def test_no_findings_closes_every_open_canary_issue(harness: Harness) -> None:
    harness.write(
        [],
        [{"number": 7, "title": "canary: a:b"}, {"number": 8, "title": "canary: c:d"}],
    )
    assert harness.run().returncode == 0
    closes = [command for command in harness.commands() if command.startswith("issue close")]
    assert [command.split()[2] for command in closes] == ["7", "8"]


def test_dry_run_prints_instead_of_running(harness: Harness) -> None:
    harness.write(
        FINDINGS[:1],
        [{"number": 9, "title": "canary: igir:update:v8.0.0"}],
    )
    result = harness.run("--dry-run")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith("dry-run: gh label create canary")
    assert any(line.startswith("dry-run: gh issue create --label canary") for line in lines)
    assert "dry-run: gh issue close 9 --comment The canary no longer reports this finding." in lines
    assert all(line.isascii() for line in lines)
    assert harness.commands() == [
        "issue list --label canary --state open --limit 200 --json number,title"
    ]


def test_label_that_already_exists_is_fine(harness: Harness) -> None:
    harness.env["STUB_LABEL_ERROR"] = 'label with name "canary" already exists'
    assert harness.run().returncode == 0


def test_other_label_errors_fail(harness: Harness) -> None:
    harness.env["STUB_LABEL_ERROR"] = "HTTP 403: Resource not accessible"
    result = harness.run()
    assert result.returncode == 1
    assert "HTTP 403" in result.stderr
    assert not [command for command in harness.commands() if command.startswith("issue")]


def test_missing_jq(harness: Harness, tmp_path: Path) -> None:
    result = harness.run(path=str(harness.bin))
    assert result.returncode == 1
    assert result.stderr == "canary-issues: jq is required but not on PATH\n"
    assert harness.commands() == []


def test_missing_gh(harness: Harness, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = harness.run(path=str(empty))
    assert result.returncode == 1
    assert result.stderr == "canary-issues: gh is required but not on PATH\n"


def test_usage_errors(harness: Harness) -> None:
    assert SH is not None
    result = subprocess.run(  # noqa: S603
        [SH, str(SCRIPT)], capture_output=True, text=True, env=harness.env, check=False
    )
    assert result.returncode == 2
    assert result.stderr.startswith("usage:")
    harness.findings.unlink()
    missing = harness.run()
    assert missing.returncode == 2
    assert "not found" in missing.stderr
