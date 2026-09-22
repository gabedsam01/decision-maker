# AGENTS.md — Decisors

## Objetivo
Decisors é uma camada provider-agnostic de decisões "System One" para agentes de IA.
Ela NÃO gera texto nem substitui o modelo principal. Recebe `state + questions` e retorna decisões tipadas com probabilidades.

## Fontes de referência
- `referencia/pi-typesafe/`: referência principal para contrato, UX do Pi, schema, batching, consentimento, budgets, TypeSafe e OpenRouter.
- `referencia/laya/`: runtime local padrão, modelos, roteamento de idioma e inferência.
- Licenças: pi-typesafe = MIT; Laya = Apache-2.0. Preservar atribuições quando código for derivado.

## Regras de produto
1. Provider padrão: `laya`, local e sem API key.
2. Providers remotos opcionais: `typesafe` (Jev oficial) e `openrouter` (Jev via Decisions API).
3. Nunca enviar dados para provider remoto por fallback silencioso. Troca para cloud exige configuração/consentimento explícitos.
4. Contrato público único: `choice`, `score`, `noul`.
5. `confidence` é concentração da distribuição, não prova, autorização ou garantia de correção.
6. Uma pergunta = um julgamento estreito. Perguntas independentes sobre o mesmo estado devem ser batchadas.
7. Não usar decisão-model para cálculo exato, lookup determinístico, geração de texto, coding ou raciocínio multi-step.
8. Não forçar decisão externa quando o modelo principal já possui uma resposta determinística no contexto.
9. Para Laya, evitar >20 opções por Choice como caminho padrão; nunca mascarar limitação com confiança alta.
10. `laya-typed-decisions` só pode ser selecionado explicitamente ou por configuração opt-in; nunca como default silencioso.

## Integração Pi
- Slash command público: `/decision`.
- Tool do agente: `decision_evaluate`.
- O adapter Pi deve ser fino e não conter lógica de providers.
- Laya deve rodar em processo Python persistente durante a sessão; nunca iniciar Python/carregar pesos a cada tool call.
- Comunicação preferida Pi ↔ Python: subprocess persistente via JSONL/stdin/stdout.
- O adapter pode ser instalado pelo CLI Python (`decisors integrate pi`) e futuramente também distribuído como pacote Pi/npm.

## Comandos esperados
- `/decision init`: primeiro setup; default Laya; baixar/preparar pesos; warm-up; teste.
- `/decision start`: habilitar decisões na sessão e carregar runtime escolhido.
- `/decision stop`: desabilitar e liberar runtime local.
- `/decision config`: escolher provider/model/device/thresholds e configurar credenciais.
- `/decision status`: provider, modelo, device, readiness, cache e uso/custo.
- `/decision test`: decisão de exemplo sem contaminar o contexto do modelo.
- `/decision doctor`: diagnóstico de runtime, pesos, dependências e credenciais.

## Configuração
- Config sem segredos: `~/.config/decisors/config.toml`.
- Cache de modelos: reutilizar cache padrão do Hugging Face.
- Segredos: preferir `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`; se houver armazenamento local, permissões owner-only.
- Default: `provider = "laya"`, `device = "auto"`, `model = "auto"`, `max_loaded = 1`.

## Limites e segurança
- OpenRouter Jev usa `/api/alpha/decisions`; não tratar como endpoint genérico OpenAI Chat Completions.
- Sem retries automáticos em decisões remotas no MVP.
- Abort/timeout devem propagar.
- Erros não podem incluir API keys, payload completo ou dados sensíveis.
- Ações destrutivas não podem ser autorizadas apenas por `confidence`.

## Escopo inicial
Core Python + CLI + adapter Pi. N8N, MCP, servidor HTTP público e adapters para outros agentes ficam fora do MVP.
