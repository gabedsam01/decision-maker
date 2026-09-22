---
description: Regras do juiz Decisors para este turno
---
Antes de agir, use o juiz. Não cole a conversa.

- Comando com exit estranho: `decision_command`. Não repita `exit=1`.
- Saída de subagente: `decision_subagent`. Não cole o recibo.
- Skill: `decision_skill`. No máximo 20. Se o pedido nomear a skill, use essa.
- Mais de 20 opções: `decision_where`. Sem chave, fica na máquina em rodadas. Com chave, pare e pergunte. Não mude para a nuvem sozinho.
- As outras escolhas vão em `decision_evaluate`: próximo passo, mesma falha, o que guardar, perguntar ou seguir, risco, chega.
- O número não autoriza apagar, publicar ou mexer em segredo.
