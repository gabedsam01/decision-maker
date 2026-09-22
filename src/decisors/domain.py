"""Provider-neutral decision request/result contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias, TypedDict, cast

from .errors import ValidationError

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
QuestionType = Literal["choice", "score", "noul"]

MAX_QUESTIONS = 32
MAX_QUESTION_ID = 128
MAX_INPUT_BYTES = 64 * 1024
MAX_INSTRUCTIONS = 4_000
MAX_CHOICE_OPTIONS = 255
MAX_SCORE_LEVELS = 10


class Question(TypedDict, total=False):
    type: QuestionType
    instructions: str
    criteria: dict[str, str | None] | list[str]


DecisionResult: TypeAlias = dict[str, Any]


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    state: JsonValue
    questions: dict[str, Question]

    @classmethod
    def from_value(
        cls,
        state: Any,
        questions: Any,
        *,
        max_input_bytes: int = MAX_INPUT_BYTES,
    ) -> DecisionRequest:
        normalized_state = _json_safe(state, "state")
        normalized_questions = _normalize_questions(questions)
        request = cls(state=normalized_state, questions=normalized_questions)
        payload = json.dumps(request.to_wire(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > max_input_bytes:
            raise ValidationError(
                f"Decision request is {len(payload)} bytes; maximum is {max_input_bytes} bytes."
            )
        return request

    def to_wire(self) -> dict[str, JsonValue]:
        return {
            "state": self.state,
            "questions": cast(dict[str, JsonValue], self.questions),
        }


def _json_safe(value: Any, label: str) -> JsonValue:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be JSON-safe.") from exc
    return cast(JsonValue, decoded)


def _normalize_questions(value: Any) -> dict[str, Question]:
    if not isinstance(value, dict) or not value:
        raise ValidationError("questions must be a non-empty object.")
    if len(value) > MAX_QUESTIONS:
        raise ValidationError(f"questions supports at most {MAX_QUESTIONS} questions per request.")

    result: dict[str, Question] = {}
    for raw_id, raw_question in value.items():
        if not isinstance(raw_id, str) or not raw_id.strip() or len(raw_id) > MAX_QUESTION_ID:
            raise ValidationError("Each question id must be a non-empty string up to 128 characters.")
        if not isinstance(raw_question, dict):
            raise ValidationError(f"Question {raw_id!r} must be an object.")

        qtype = raw_question.get("type")
        if qtype not in {"choice", "score", "noul"}:
            raise ValidationError(f"Question {raw_id!r} has unsupported type {qtype!r}.")

        instructions = raw_question.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValidationError(f"Question {raw_id!r} requires non-empty instructions.")
        if len(instructions) > MAX_INSTRUCTIONS:
            raise ValidationError(
                f"Question {raw_id!r} instructions exceed {MAX_INSTRUCTIONS} characters."
            )

        question: Question = {"type": cast(QuestionType, qtype), "instructions": instructions.strip()}

        if qtype == "choice":
            criteria = raw_question.get("criteria")
            if isinstance(criteria, list):
                criteria = {item: None for item in criteria if isinstance(item, str)}
            if not isinstance(criteria, dict):
                raise ValidationError(f"Choice {raw_id!r} criteria must be an object.")
            if not 2 <= len(criteria) <= MAX_CHOICE_OPTIONS:
                raise ValidationError(
                    f"Choice {raw_id!r} requires 2-{MAX_CHOICE_OPTIONS} options."
                )
            normalized: dict[str, str | None] = {}
            for key, description in criteria.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValidationError(f"Choice {raw_id!r} has an invalid option key.")
                if description is not None and not isinstance(description, str):
                    raise ValidationError(
                        f"Choice {raw_id!r} option descriptions must be strings or null."
                    )
                normalized[key] = description
            question["criteria"] = normalized
        elif qtype == "score":
            criteria = raw_question.get("criteria")
            if not isinstance(criteria, list) or not all(isinstance(item, str) for item in criteria):
                raise ValidationError(f"Score {raw_id!r} criteria must be an ordered string array.")
            if not 2 <= len(criteria) <= MAX_SCORE_LEVELS:
                raise ValidationError(
                    f"Score {raw_id!r} requires 2-{MAX_SCORE_LEVELS} ordered levels."
                )
            question["criteria"] = [item for item in criteria]
        elif "criteria" in raw_question and raw_question["criteria"] not in (None, [], {}):
            raise ValidationError(f"Noul {raw_id!r} does not accept criteria.")

        result[raw_id] = question
    return result


def validate_result(request: DecisionRequest, value: Any) -> DecisionResult:
    if not isinstance(value, dict):
        raise ValidationError("Provider returned a non-object response.")
    model = value.get("model")
    answers = value.get("answers")
    usage = value.get("usage")
    if not isinstance(model, str) or not model:
        raise ValidationError("Provider response is missing model.")
    if not isinstance(answers, dict) or set(answers) != set(request.questions):
        raise ValidationError("Provider response answers do not match requested question ids.")
    if not isinstance(usage, dict):
        raise ValidationError("Provider response is missing usage.")

    for question_id, question in request.questions.items():
        answer = answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ValidationError(f"Provider returned an invalid answer for {question_id!r}.")
        qtype = question["type"]
        if qtype == "noul":
            _probability(answer.get("noul"), f"{question_id}.noul")
        else:
            confidence = answer.get("confidence")
            _probability(confidence, f"{question_id}.confidence")
            probabilities = answer.get("probabilities")
            if not isinstance(probabilities, dict) or not probabilities:
                raise ValidationError(f"{question_id}.probabilities must be a non-empty object.")
            for key, probability in probabilities.items():
                if not isinstance(key, str):
                    raise ValidationError(f"{question_id}.probabilities has a non-string key.")
                _probability(probability, f"{question_id}.probabilities[{key!r}]")
            if qtype == "choice":
                criteria = cast(dict[str, str | None], question["criteria"])
                if answer.get("choice") not in criteria:
                    raise ValidationError(f"{question_id}.choice is not one of the supplied options.")
            else:
                score = answer.get("score")
                if not isinstance(score, (int, float)) or isinstance(score, bool):
                    raise ValidationError(f"{question_id}.score must be numeric.")
    return cast(DecisionResult, value)


def _probability(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"{label} must be numeric.")
    probability = float(value)
    if not 0.0 <= probability <= 1.0:
        raise ValidationError(f"{label} must be between 0 and 1.")
    return probability
