"""Narrow wrappers around choice/score/noul. No text generation, no authorization."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .errors import ValidationError

LOCAL_CAP = 20
CLOUD_CAP = 255
OTHER = "nenhuma destas"
MIN_SCORE = 0.5
MIN_GAP = 0.2
Choose = Callable[[list[str]], str]
Score = Callable[[str], float]


def command_report(command: str, exit_code: int, stdout: str = "", stderr: str = "") -> dict[str, Any]:
    out = stdout or ""
    err = stderr or ""
    blob = f"{out}\n{err}".lower()
    name = _command_name(command)
    if _destructive(command):
        return _fixed("risco", "Marcado como perigoso. Não autorizado.")
    if _truncated(blob):
        return _fixed("truncado", "A saída foi cortada. Leia o arquivo salvo, não o rabo.")
    if exit_code == 0:
        return _fixed("ok", _clip(out) or "Terminou sem erro.")
    if name in {"rg", "grep", "egrep", "fgrep", "fd"} and exit_code == 1 and not out.strip():
        return _fixed("vazio", "Nada encontrado. Não é falha.")
    if _quirk(name, err, blob):
        return _fixed("quirk", "A ferramenta não existe neste runner. Não repita o comando.")
    if "traceback" in blob or "syntaxerror" in blob:
        return _fixed("falhou", _clip(err) or "O comando falhou.")
    return {
        "verdict": "incerto",
        "say": "Exit diferente de zero, fora da tabela. Não repita igual.",
        "needs_model": True,
        "authorized": False,
    }


def subagent_report(status: str, output: str = "", error: str = "") -> dict[str, Any]:
    text = output or ""
    err = error or ""
    blob = f"{text}\n{err}".lower()
    state = (status or "").lower()
    if any(mark in blob for mark in ("invalid configuration", "fallbackmodels", "removed frontmatter")):
        return _agent("infra", "Não chegou a rodar. Não repita igual.", False)
    if state in {"unavailable", "error"} and not text.strip():
        return _agent("infra", "Não chegou a rodar. Não repita igual.", False)
    if state in {"failed", "error"} and not text.strip():
        return _agent("vazio", "Sem resposta.", False)
    if state in {"ok", "completed", "complete", "success"} and text.strip():
        return _agent("resposta", _clip(text), False)
    if text.strip():
        return {
            "verdict": "incerto",
            "say": _clip(text),
            "retry": False,
            "needs_model": True,
            "authorized": False,
        }
    return _agent("vazio", "Sem resposta.", False)


def skill_shortlist(
    task: str,
    catalog: list[dict[str, Any] | str],
    limit: int = 19,
) -> dict[str, Any]:
    if limit < 1 or limit > 19:
        raise ValidationError("A shortlist local fica entre 1 e 19.")
    names: list[tuple[str, str]] = []
    for item in catalog:
        if isinstance(item, str):
            s = item.strip()
            if s:
                names.append((s, ""))
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append((name, str(item.get("description") or "")))
    named = _named_skill(task, [name for name, _desc in names])
    if named:
        return {
            "shortlist": [{"name": named, "description": ""}],
            "recommended": named,
            "choice": named,
            "say": f"O pedido já nomeou {named}.",
            "capped": False,
            "needs_model": False,
        }
    scored = sorted(
        ((_overlap(task, f"{name} {desc}"), name, desc) for name, desc in names),
        key=lambda row: (-row[0], row[1]),
    )
    picked = [row for row in scored if row[0] > 0][:limit] or scored[:limit]
    shortlist = [{"name": name, "description": desc} for _score, name, desc in picked]
    recommended = shortlist[0]["name"] if shortlist else None
    say = f"Use {recommended}." if recommended else "Nenhuma skill encaixa."
    return {
        "shortlist": shortlist,
        "recommended": recommended,
        "choice": recommended,
        "say": say,
        "capped": len(names) > limit,
        "needs_model": False,
    }


def where_plan(
    option_count: int,
    credentials: dict[str, Any],
    cloud_allowed: bool | None = None,
) -> dict[str, Any]:
    if option_count < 2:
        raise ValidationError("Precisa de pelo menos 2 opções.")
    if option_count > CLOUD_CAP:
        raise ValidationError("No máximo 255 opções.")
    if credentials.get("typesafe"):
        provider = "typesafe"
    elif credentials.get("openrouter"):
        provider = "openrouter"
    else:
        provider = None
    if option_count <= LOCAL_CAP:
        return {"mode": "local", "say": "Cabe na máquina.", "provider": None, "authorized": False}
    if provider is None or cloud_allowed is False:
        return {
            "mode": "local_loop",
            "say": "Mais de 20 opções. Sigo na máquina, em rodadas.",
            "provider": None,
            "authorized": False,
        }
    if cloud_allowed is True:
        return {
            "mode": "cloud",
            "say": f"Uma chamada em {provider}.",
            "provider": provider,
            "authorized": False,
        }
    return {
        "mode": "ask",
        "say": f"Não cabe em 20 opções. Posso usar {provider} e concluir de uma vez?",
        "provider": provider,
        "authorized": False,
    }


def shape_text(state: Any, instructions: str) -> tuple[dict[str, str], str, bool]:
    """Put the fact where Laya reads it. An empty state is routed to the English model."""
    if isinstance(state, dict) and state:
        text = " ".join(str(value) for value in state.values())
        shaped = {str(key): str(value) for key, value in state.items()}
        shaped.setdefault("texto", text)
        return shaped, instructions or "Qual opção o `texto` pede?", _portuguese(text)
    text = state.strip() if isinstance(state, str) else ""
    if not text:
        text = (instructions or "").strip()
    shaped = {"texto": text}
    question = (instructions or "").strip() or "Qual opção o `texto` pede?"
    if "texto" not in question:
        question = question + " Use o campo `texto`."
    return shaped, question, _portuguese(text)


def pick_scored(scores: dict[str, float]) -> dict[str, Any]:
    if len(scores) < 2:
        raise ValidationError("Precisa de pelo menos 2 opções.")
    ranked = sorted(scores.items(), key=lambda item: (-float(item[1]), item[0]))
    top, second = ranked[0], ranked[1]
    if float(top[1]) < MIN_SCORE or float(top[1]) - float(second[1]) < MIN_GAP:
        return {
            "choice": None,
            "say": "Não deu para separar. Não escolhi a primeira da lista.",
            "scores": scores,
            "authorized": False,
        }
    return {
        "choice": top[0],
        "say": f"Ficou em {top[0]}. Na máquina.",
        "scores": scores,
        "authorized": False,
    }


NUMBERS_PT = {
    0: "zero", 1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco",
    6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez",
    11: "onze", 12: "doze", 13: "treze", 14: "quatorze", 15: "quinze",
    16: "dezesseis", 17: "dezessete", 18: "dezoito", 19: "dezenove", 20: "vinte",
    21: "vinte e um", 22: "vinte e dois", 23: "vinte e três", 24: "vinte e quatro",
    25: "vinte e cinco", 26: "vinte e seis", 27: "vinte e sete", 28: "vinte e oito",
    29: "vinte e nove", 30: "trinta", 40: "quarenta", 50: "cinquenta",
    60: "sessenta", 70: "setenta", 80: "oitenta", 90: "noventa", 100: "cem",
}
NUMBERS_EN = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
    21: "twenty-one", 22: "twenty-two", 23: "twenty-three", 24: "twenty-four",
    25: "twenty-five", 26: "twenty-six", 27: "twenty-seven", 28: "twenty-eight",
    29: "twenty-nine", 30: "thirty", 40: "forty", 50: "fifty",
    60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety", 100: "one hundred",
}


def expand_label(label: str, portuguese: bool) -> str:
    cleaned = str(label).strip()
    try:
        val = int(cleaned)
        word_table = NUMBERS_PT if portuguese else NUMBERS_EN
        if val in word_table:
            sep = " ou " if portuguese else " or "
            return f"{cleaned}{sep}{word_table[val]}"
    except ValueError:
        pass
    inv_table = {v: k for k, v in (NUMBERS_PT.items() if portuguese else NUMBERS_EN.items())}
    if cleaned.lower() in inv_table:
        digit = str(inv_table[cleaned.lower()])
        sep = " ou " if portuguese else " or "
        return f"{cleaned}{sep}{digit}"
    return cleaned


def conclude_scored(options: list[str], score: Score) -> dict[str, Any]:
    pending = _unique(options)
    if len(pending) < 2:
        raise ValidationError("Precisa de pelo menos 2 opções.")
    if len(pending) > CLOUD_CAP:
        raise ValidationError("No máximo 255 opções.")
    rounds = 0
    while len(pending) > LOCAL_CAP:
        rounds += 1
        if rounds > 16:
            raise ValidationError("O loop local não concluiu.")
        winners: list[str] = []
        for chunk in _chunks(pending, LOCAL_CAP):
            if len(chunk) == 1:
                winners.append(chunk[0])
                continue
            picked = pick_scored({item: score(item) for item in chunk})
            if not picked["choice"]:
                return picked
            winners.append(str(picked["choice"]))
        pending = list(dict.fromkeys(winners))
        if len(pending) < 2:
            break
    rounds += 1
    if len(pending) == 1:
        return {
            "choice": pending[0],
            "rounds": rounds,
            "mode": "local_loop" if len(_unique(options)) > LOCAL_CAP else "local",
            "say": f"Ficou em {pending[0]}. Na máquina.",
            "authorized": False,
        }
    result = pick_scored({item: score(item) for item in pending})
    result["rounds"] = rounds
    result["mode"] = "local_loop" if len(_unique(options)) > LOCAL_CAP else "local"
    return result


def conclude_local(options: list[str], choose: Choose) -> dict[str, Any]:
    pending = _unique(options)
    if len(pending) < 2:
        raise ValidationError("Precisa de pelo menos 2 opções.")
    if len(pending) > CLOUD_CAP:
        raise ValidationError("No máximo 255 opções.")
    rounds = 0
    # ponytail: tournament of 19, not a learned shortlist. Upgrade path is an explicit cloud yes.
    while len(pending) > LOCAL_CAP:
        rounds += 1
        if rounds > 16:
            raise ValidationError("O loop local não concluiu.")
        winners: list[str] = []
        for chunk in _chunks(pending, LOCAL_CAP - 1):
            if len(chunk) == 1:
                winners.append(chunk[0])
                continue
            asked = chunk + [OTHER]
            if len(asked) > LOCAL_CAP:
                raise ValidationError("Rodada local passou de 20 opções.")
            picked = choose(asked)
            if picked not in asked:
                raise ValidationError("A rodada devolveu uma opção que não estava na lista.")
            if picked in chunk:
                winners.append(picked)
        if not winners:
            raise ValidationError("Nenhuma opção sobrou. A rodada recusou todas.")
        pending = list(dict.fromkeys(winners))
    rounds += 1
    chosen = pending[0] if len(pending) == 1 else choose(pending)
    if chosen not in pending:
        raise ValidationError("A rodada devolveu uma opção que não estava na lista.")
    return {
        "choice": chosen,
        "rounds": rounds,
        "mode": "local_loop" if len(_unique(options)) > LOCAL_CAP else "local",
        "say": f"Ficou em {chosen}. Na máquina.",
        "authorized": False,
    }


def _fixed(verdict: str, say: str) -> dict[str, Any]:
    return {"verdict": verdict, "say": say, "needs_model": False, "authorized": False}


def _agent(verdict: str, say: str, retry: bool) -> dict[str, Any]:
    return {"verdict": verdict, "say": say, "retry": retry, "needs_model": False, "authorized": False}


def _command_name(command: str) -> str:
    token = (command or "").strip().split()
    if not token:
        return ""
    return token[0].rsplit("/", 1)[-1]


def _destructive(command: str) -> bool:
    text = (command or "").lower()
    marks = ("rm -rf", "git push", "git reset --hard", "mkfs", "dd if=", "chmod 777", "curl | sh", ":(){")
    return any(mark in text for mark in marks)


def _truncated(blob: str) -> bool:
    return "truncat" in blob or "full output is saved" in blob


def _quirk(name: str, err: str, blob: str) -> bool:
    if name in {"type", "which"} and "no such file" in blob:
        return True
    return "trying to start process" in blob or "command not found" in err.lower()


def _clip(text: str, limit: int = 240) -> str:
    line = " ".join((text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def _portuguese(text: str) -> bool:
    lowered = text.lower()
    return any(mark in lowered for mark in ("não", "ção", "ã", "õ", "ç", "á", "é", "í", "ó", "ú"))


def _tokens(text: str) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9]{3,}", text.lower())}


def _overlap(task: str, haystack: str) -> int:
    task_tokens = _tokens(task)
    hay_tokens = _tokens(haystack)
    score = 0
    for tt in task_tokens:
        if tt in hay_tokens:
            score += 2
        elif len(tt) >= 4 and any(tt in ht or (len(ht) >= 4 and ht in tt) for ht in hay_tokens):
            score += 1
    return score


def _named_skill(task: str, names: list[str]) -> str | None:
    lowered = task.lower()
    hits = []
    for name in names:
        if re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", lowered):
            hits.append(name)
    if not hits:
        return None
    return max(hits, key=len)


def _unique(options: list[str]) -> list[str]:
    if not isinstance(options, list) or not all(isinstance(item, str) and item.strip() for item in options):
        raise ValidationError("Opções precisam ser uma lista de textos.")
    return list(dict.fromkeys(item.strip() for item in options))


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
