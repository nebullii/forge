"""Tests for artifact models — frozen dataclasses and union types."""

import pytest

from src.collaboration.models import (
    CodeArtifact,
    DecisionArtifact,
    ReviewArtifact,
    ContractArtifact,
    BuildLogArtifact,
    ReworkRequestArtifact,
)


class TestCodeArtifact:
    def test_creation(self):
        art = CodeArtifact(path="a.py", content="x=1", producer_agent="backend")
        assert art.path == "a.py"
        assert art.content == "x=1"
        assert art.version == 1
        assert art.artifact_type == "code"

    def test_frozen(self):
        art = CodeArtifact(path="a.py", content="x", producer_agent="b")
        with pytest.raises(AttributeError):
            art.content = "modified"

    def test_created_at_auto_set(self):
        art = CodeArtifact(path="a.py", content="x", producer_agent="b")
        assert art.created_at  # non-empty string

    def test_custom_fields(self):
        art = CodeArtifact(
            path="a.py", content="x", producer_agent="b",
            artifact_type="config", language="python",
            tags=("setup", "config"), version=3,
        )
        assert art.artifact_type == "config"
        assert art.language == "python"
        assert art.tags == ("setup", "config")
        assert art.version == 3


class TestDecisionArtifact:
    def test_creation(self):
        art = DecisionArtifact(key="stack", value={"lang": "go"}, producer_agent="planner")
        assert art.key == "stack"
        assert art.value == {"lang": "go"}

    def test_frozen(self):
        art = DecisionArtifact(key="k", value="v", producer_agent="p")
        with pytest.raises(AttributeError):
            art.key = "changed"


class TestReviewArtifact:
    def test_defaults(self):
        art = ReviewArtifact(target_path="", producer_agent="reviewer")
        assert art.passed is True
        assert art.issues == ()

    def test_with_issues(self):
        art = ReviewArtifact(
            target_path="a.py", producer_agent="reviewer",
            passed=False, issues=({"msg": "bad"},),
        )
        assert art.passed is False
        assert len(art.issues) == 1


class TestBuildLogArtifact:
    def test_defaults(self):
        art = BuildLogArtifact(message="hello")
        assert art.level == "info"
        assert art.producer_agent == ""

    def test_error_level(self):
        art = BuildLogArtifact(message="fail", level="error", producer_agent="ci")
        assert art.level == "error"


class TestReworkRequestArtifact:
    def test_creation(self):
        art = ReworkRequestArtifact(
            target_path="a.py", original_agent="backend",
            issue="SQL injection", producer_agent="reviewer",
        )
        assert art.target_path == "a.py"
        assert art.original_agent == "backend"
        assert art.issue == "SQL injection"

    def test_frozen(self):
        art = ReworkRequestArtifact(
            target_path="a.py", original_agent="backend", issue="fix",
        )
        with pytest.raises(AttributeError):
            art.issue = "changed"


class TestContractArtifact:
    def test_creation(self):
        art = ContractArtifact(
            contract_type="api",
            data={"method": "GET", "path": "/users"},
            producer_agent="backend",
        )
        assert art.contract_type == "api"
        assert art.data["method"] == "GET"
