# Tools do complemento

Contrato público continua `choice`, `score`, `noul`. Estas tools só classificam ou montam a pergunta. Não geram texto e não autorizam ação.

## Tools no Pi

| Tool | Tipo | Entrada | Saída |
|---|---|---|---|
| `decision_command` | determinística | comando, exit, stdout, stderr | uma frase: ok, vazio, quirk, truncado, falhou, risco, incerto |
| `decision_subagent` | determinística | status, output, error | resposta, infra, vazio ou incerto. Infra não pede retry |
| `decision_skill` | determinística | pedido + catálogo | no máximo 19 skills. Se o pedido nomeia uma, fica nela |
| `decision_where` | mista | lista de opções | plano: local, loop local, perguntar, ou nuvem |

`decision_evaluate` continua sendo o lugar das seis escolhas estreitas: próximo passo, mesma falha, o que guardar, perguntar ou seguir, risco, chega. Os modelos estão na skill `decisores-decisoes`.

## Tool 9

Fonte das chaves: `catalog.credentials` (`openrouter`, `typesafe`). Só booleano. A chave não entra na resposta.

- Até 20 opções: uma rodada local.
- Mais de 20 e sem chave: loop local até sobrar uma. A frase não menciona nuvem.
- Mais de 20, com chave, sem resposta do usuário: `ask`. Não chama provedor remoto.
- Usuário diz não: o mesmo loop local.
- Usuário diz sim: uma chamada no provedor da chave (TypeSafe se as duas existirem), com `model=auto`, sem gravar config e sem armar o consentimento da sessão.
- Sem interface para perguntar: devolve `ask` e não chama modelo.

O loop local recusa provider que não seja `laya`. Não há fallback silencioso.
