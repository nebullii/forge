"""Tests for the new JSON file extraction and path normalization helpers."""

from pathlib import Path

from src.agents.base import BaseAgent, normalize_paths_against_plan
from src.providers.base import BaseProvider, ProviderConfig


class _NullProvider(BaseProvider):
    def chat(self, messages, system="", **options):
        return ""

    def stream(self, messages, system="", **options):
        yield ""


def _agent(tmp_path):
    return BaseAgent(_NullProvider(ProviderConfig(name="fake", model="m")), tmp_path)


def test_extract_files_parses_clean_json(tmp_path):
    response = '''
    {
      "files": [
        {"path": "index.html", "content": "<!doctype html>\\n<html></html>"},
        {"path": "styles.css", "content": "body { color: red; }"}
      ]
    }
    '''
    files = _agent(tmp_path).extract_files(response)
    assert len(files) == 2
    assert files[0][0] == "index.html"
    assert files[0][1].endswith("\n")
    assert files[1][0] == "styles.css"


def test_extract_files_strips_leading_slash(tmp_path):
    response = '{"files": [{"path": "/etc/passwd", "content": "x"}]}'
    files = _agent(tmp_path).extract_files(response)
    assert files == [("etc/passwd", "x\n")]


def test_extract_files_falls_back_to_markdown_when_json_invalid(tmp_path):
    response = "```file:index.html\n<html></html>\n```"
    files = _agent(tmp_path).extract_files(response)
    assert files == [("index.html", "<html></html>\n")]


def test_extract_files_handles_json_surrounded_by_prose(tmp_path):
    response = (
        "Sure, here are the files you asked for:\n"
        '{"files": [{"path": "a.txt", "content": "hello"}]}\n'
        "Hope that helps!"
    )
    files = _agent(tmp_path).extract_files(response)
    assert files == [("a.txt", "hello\n")]


def test_extract_files_ignores_non_files_json(tmp_path):
    # JSON envelope without a `files` array should fall through to markdown
    response = '{"thoughts": "hmm"}\n```file:x.py\nprint(1)\n```'
    files = _agent(tmp_path).extract_files(response)
    assert files == [("x.py", "print(1)\n")]


# -- Path normalization --------------------------------------------------


def test_normalize_paths_corrects_unexpected_frontend_prefix():
    # The pomodoro bug exactly
    generated = [("frontend/index.html", "<html>hi</html>\n")]
    planned = ["index.html", "styles.css", "script.js"]
    fixed = normalize_paths_against_plan(generated, planned)
    assert fixed == [("index.html", "<html>hi</html>\n")]


def test_normalize_paths_leaves_correct_paths_alone():
    generated = [("backend/main.py", "x"), ("frontend/src/App.jsx", "y")]
    planned = ["backend/main.py", "frontend/src/App.jsx"]
    assert normalize_paths_against_plan(generated, planned) == generated


def test_normalize_paths_handles_ambiguous_basenames_conservatively():
    # Two planned files share a basename — don't try to guess which.
    generated = [("anywhere/index.html", "x")]
    planned = ["index.html", "docs/index.html"]
    fixed = normalize_paths_against_plan(generated, planned)
    # Conservative: leave the original path so a downstream verifier can complain
    assert fixed == [("anywhere/index.html", "x")]


def test_normalize_paths_when_no_match_keeps_generated():
    generated = [("totally/new/file.txt", "x")]
    planned = ["index.html"]
    assert normalize_paths_against_plan(generated, planned) == [("totally/new/file.txt", "x")]


def test_normalize_paths_strips_leading_slash():
    generated = [("/index.html", "x")]
    planned = ["index.html"]
    assert normalize_paths_against_plan(generated, planned) == [("index.html", "x")]
