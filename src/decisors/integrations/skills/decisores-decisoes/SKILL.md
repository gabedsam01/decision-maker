---
name: decisores-decisoes
description: Use quando o turno precisa de uma escolha estreita do Decisors — filtrar comando, filtrar subagente, escolher skill, ou decidir se cabe na máquina. Não use para programar, calcular ou escrever.
---

# Decisores — decisões estreitas

O juiz escolhe ou diz sim/não. Quem escreve é o agente. O número não autoriza apagar, publicar ou mexer em segredo.

## Quando usar as tools

- `decision_command` — o comando devolveu exit estranho. Não repita `exit=1` sem ler a frase.
- `decision_subagent` — chegou recibo de subagente. Use a frase. Não cole o JSON.
- `decision_skill` — antes de carregar skill. No máximo 19. Se o pedido nomear uma, use essa.
- `decision_where` — a lista tem mais de 20 opções. Sem chave, fica na máquina em rodadas. Com chave, pare e pergunte. Não mude para a nuvem sozinho.
- `decision_evaluate` — as seis escolhas abaixo. Uma pergunta por julgamento. Perguntas independentes vão na mesma chamada.

Estado = pedido + último erro + arquivos. Não cole a conversa.

## Modelos prontos

Próximo passo:

```json
{"proximo": {"type": "choice", "instructions": "Qual é o próximo passo, um só?", "criteria": {"ler": null, "buscar": null, "comando": null, "web": null, "perguntar": null, "parar": null}}}
```

Mesma falha:

```json
{"mesma": {"type": "noul", "instructions": "Este erro é o mesmo da tentativa anterior?"}}
```

O que guardar:

```json
{"guardar": {"type": "noul", "instructions": "O próximo passo precisa deste trecho?"}}
```

Perguntar ou seguir:

```json
{"falta": {"type": "noul", "instructions": "Falta um fato que muda o que vai ser feito?"}}
```

Risco:

```json
{"risco": {"type": "noul", "instructions": "Este passo apaga, publica ou mexe em segredo?"}}
```

Chega:

```json
{"chega": {"type": "noul", "instructions": "A resposta já basta para encerrar o turno?"}}
```

Se `risco` vier alto, pare e pergunte. Não trate o número como permissão.
