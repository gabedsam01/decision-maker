import pytest

from decisors.domain import DecisionRequest, validate_result
from decisors.errors import ValidationError


def sample_request() -> DecisionRequest:
    return DecisionRequest.from_value(
        {"message": "charged twice"},
        {
            "team": {
                "type": "choice",
                "instructions": "Which team?",
                "criteria": {"billing": "payments", "other": None},
            },
            "urgent": {
                "type": "noul",
                "instructions": "Is this urgent?",
            },
            "severity": {
                "type": "score",
                "instructions": "How severe?",
                "criteria": ["minor", "major", "critical"],
            },
        },
    )


def test_normalizes_supported_question_types() -> None:
    request = sample_request()
    assert request.questions["team"]["type"] == "choice"
    assert request.questions["severity"]["criteria"] == ["minor", "major", "critical"]


def test_rejects_choice_without_escape_room() -> None:
    with pytest.raises(ValidationError, match="requires 2-255 options"):
        DecisionRequest.from_value(
            "x",
            {
                "only": {
                    "type": "choice",
                    "instructions": "Pick",
                    "criteria": {"one": "only option"},
                }
            },
        )


def test_rejects_non_json_state() -> None:
    with pytest.raises(ValidationError, match="JSON-safe"):
        DecisionRequest.from_value({"bad": object()}, {"q": {"type": "noul", "instructions": "ok?"}})


def test_validates_provider_result() -> None:
    request = sample_request()
    result = validate_result(
        request,
        {
            "model": "test",
            "usage": {"input_tokens": 12, "output_tokens": 0},
            "answers": {
                "team": {
                    "type": "choice",
                    "choice": "billing",
                    "probabilities": {"billing": 0.9, "other": 0.1},
                    "confidence": 0.8,
                },
                "urgent": {"type": "noul", "noul": 0.7},
                "severity": {
                    "type": "score",
                    "score": 1.2,
                    "probabilities": {"0": 0.1, "1": 0.6, "2": 0.3},
                    "confidence": 0.5,
                },
            },
        },
    )
    assert result["answers"]["team"]["choice"] == "billing"


def test_rejects_choice_not_in_criteria() -> None:
    request = DecisionRequest.from_value(
        "x",
        {
            "q": {
                "type": "choice",
                "instructions": "Pick",
                "criteria": {"a": None, "b": None},
            }
        },
    )
    with pytest.raises(ValidationError, match="not one of"):
        validate_result(
            request,
            {
                "model": "bad",
                "usage": {"input_tokens": 1, "output_tokens": 0},
                "answers": {
                    "q": {
                        "type": "choice",
                        "choice": "c",
                        "probabilities": {"a": 0.5, "b": 0.5},
                        "confidence": 0.0,
                    }
                },
            },
        )
