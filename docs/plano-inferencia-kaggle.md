# Plano: inferência fora da CPU local

Só viabilidade. Sem ferramenta, sem personalização, sem implementação.

Data das fontes: 2026-09-21. O clone em `referencia/laya` estava 9 commits atrás de `origin/main` (`v0.3.5`, último commit `573e5b6`, 2026-09-21 23:47 +0530).

## Veredito

A proposta **não é viável** do jeito descrito: apertar `S` e receber JSON em milissegundos.

Cold start de **kernel** existe e foi medido nesta conta, só pela REST, sem MCP e sem CLI. Não é scale-to-zero. É `SaveKernel`, que sobe um job.

Medido em 2026-09-21, conta `gabedsam01`, script privado, CPU, sem internet, sem peso:

| passo | tempo |
|---|---|
| `POST api.kaggle.com/v1/kernels.KernelsApiService/SaveKernel` | 1,4 s, HTTP 200, `versionNumber` 1, kernel `135302787` |
| primeiro status | `RUNNING` |
| `COMPLETE` | 10,6 s depois do push |
| stdout do script (`DECISORS_PROBE_OK`) | 1,0 s de relógio da sessão |

Notebook: `gabedsam01/decisors-rest-probe`. O job acabou. Não ficou um URL escutando.

Cota lida no mesmo dia, `GetAcceleratorQuotaStatistics`: GPU 0 / 108000 s (30 h), TPU 0 / 72000 s (20 h), refresh `2026-09-26T00:00:00Z`. Os notebooks já existentes são blender/diag. Nenhum é servidor. Status amostrado: `COMPLETE`, um `CANCEL_ACKNOWLEDGED`.

Informar a API do Kaggle e apertar `S` **não** produz inferência síncrona. A API pública não tem endpoint de serving. Ela manda notebook rodar. Notebook não aceita o `state` do `/decision` como request HTTP.

O que a API key compra:

- download de dataset e de model (`kagglehub`, CLI, `GET /api/v1/models/.../download`)
- `kernels push` / `status` / `output` / `logs` — batch, arquivo de saída, não request/response
- OAuth com escopos `datasets.*`, `models.*`, `kernels.get|update|execute`

O que ela não compra: um URL estável que receba uma decisão e devolva JSON em dezenas ou centenas de milissegundos.

O MCP em `https://www.kaggle.com/mcp` ([docs](https://www.kaggle.com/docs/mcp)) não muda isso. As tools são notebook (criar sessão, status `QUEUED|RUNNING|COMPLETE|ERROR`, save-and-run, baixar output), dataset, model, competition, benchmark e hackathon. Não há tool `predict` nem `infer`. `create_notebook_session` devolve uma operation longa, não um endpoint.

O dataset público com os pesos resolve só a **distribuição**. Isso já está resolvido, sem key nenhuma, no Hugging Face, licença Apache 2.0 dos pesos:

- `convaiinnovations/laya` (inglês, ~808 MB)
- `convaiinnovations/laya-multilingual` (~647 MB)
- `convaiinnovations/laya-typed-decisions`

Fonte: card do modelo e README do Laya. "Weights | Apache 2.0 | Open weights, on-premise capable".

## Os três pontos, no enquadramento certo

### 1. Lazy start e idle timeout

No Kaggle a resposta é **não**. Não existe scale-to-zero.

Cota oficial atual, [Efficient GPU Usage](https://www.kaggle.com/docs/efficient-gpu-usage): "30 hours or sometimes higher depending on demand and resources". Reset semanal. Staff (2020, ainda citado) garante piso de 30 h e reset sábado 00:00 UTC. A cota flutua. Não é contrato.

Sessão, [Notebooks / Technical Specifications](https://www.kaggle.com/docs/notebooks): 12 h de execução em CPU/GPU, 9 h em TPU. Idle da sessão interativa: **20 minutos** nessa página. A página de GPU diz que a sessão interativa fica viva até **60 minutos** de idle se você não parar. As duas páginas oficiais discordam. O que não discorda: minuto com acelerador ligado conta na cota, esteja o modelo ocioso ou não.

GPU não é garantida: "in busy times, you might be placed in a queue". Hardware documentado: P100, T4 x2, TPU. Não dá para cravar T4.

`SaveKernel` / `kernels push` sobe um job, espera, baixa arquivo. O cold start vazio, CPU, sem fila, foi 12 s até `COMPLETE`. Isso já estoura o `/decision` interativo. O p50 local nesta máquina é 1300 ms. GPU com fila, peso e túnel não foi medido. Quem faz "servidor no Kaggle" (endpoint-vps, ShadowGPU, ngrok) não usa um endpoint do Kaggle: o notebook não termina, abre túnel Cloudflare/ngrok, e o cliente lê a URL no log ou no ntfy. Ocioso conta na cota até um `cancel` explícito.

O atalho que circula (Ollama/ngrok dentro do notebook, posts no X de 6–7 set 2026 sobre TPU com "endpoint OpenAI") é hack de sessão. O próprio post admite: não substitui servidor dedicado; ~20 h TPU/semana, sessão de 9 h. Não é API do Kaggle. Não entra no produto.

### 2. Fallback para CPU local

Obrigatório, e nunca silencioso. Regra 3 do projeto: troca de provedor exige consentimento explícito, nos dois sentidos.

Motivo visível, um destes, sem misturar:

- key ausente ou recusada
- cota zerada
- fila de GPU sem vaga no prazo
- sessão morta (idle, teto de 12 h, kernel morto)
- timeout de cold start
- rede
- versão do peso diferente da pinada

O `state` do usuário sai da máquina. Isso não herda o consentimento do OpenRouter/TypeSafe. Campo próprio, opt-in, antes do primeiro egresso.

A key fica em arquivo 600. A TUI só diz se existe. Nunca desenha o segredo.

### 3. Versionamento

Sim, para **pesos**. Não para servir.

Kaggle Models: handle `owner/model/framework/variation/version_number`. "Versions are like checkpoints." Nova versão é outro número. Download endereça a versão (`.../1/download`). Dataset: até 200 GB por dataset, 200 GB no total privado, uma fonte por dataset, e a doc fala em versionar. `kaggle datasets version` existe no CLI.

O que importa no Decisors é pin por hash, no mesmo espírito do checksum de migration. Fora do notebook, `kagglehub` grava em `~/.cache/kagglehub/`. O download sem número pega "latest"; o download com `/1` ou `/versions/1` pega aquela versão. `force_download=True` ignora o cache. A doc não diz que um "latest" já cacheado se invalida sozinho quando sai versão nova. Pin no número, e hash por cima.

HF já tem revision/commit. Pin lá é mais simples que espelhar no Kaggle.

## O que o Laya mudou hoje (v0.3.5)

O clone local não tem isso ainda. Não muda o veredito do Kaggle. Muda o que "remoto" compraria:

- `8e58a6c`: latim indeciso **não** é mais tratado como inglês. Texto curto sem acento e com function word inglesa ainda cai em english de propósito ("Care este ora in Tokyo?"). O bug do benchmark ("Fui cobrado duas vezes" → english) pode continuar nesse caso. Não foi medido neste plano.
- `62f4f15`: shortlist por embedding para choice grande. **Opt-in**, `embed_fn` do chamador. O `predict` padrão não muda. O teto de ~20 opções (Banking77 0.425 vs Jev 0.870) continua no caminho padrão, local ou remoto.
- Temperaturas clamped em [0.5, 5.0]. Muda confiança, não o argmax.
- Download só dos arquivos do checkpoint pedido. Lifecycle do router thread-safe.

## Matriz

| opção | endpoint HTTP persistente | scale-to-zero | cold start | grátis de verdade | segredo | licença dos pesos | versionamento |
|---|---|---|---|---|---|---|---|
| CPU local (hoje) | não precisa | n/a | 118 s na 1ª carga medida; depois p50 1300 ms | sim | nenhum | Apache 2.0 | pin HF |
| Dataset/Model Kaggle + API key | **não** | **não** | minutos (fila + boot) | cota 30 h+/semana, queima com o notebook de pé | key do usuário | Apache 2.0 se republicar | versões numeradas, sim |
| Notebook + túnel (ngrok) | hack, URL morre | não | fila + boot | mesma cota, ocioso conta | key + token do túnel | n/a | n/a |
| HF, download local | não precisa | n/a | download uma vez | sim | nenhum (gated não se aplica) | Apache 2.0 | revision |
| Space `laya-demo` ZeroGPU | Gradio, não API de produto | GPU solta depois da chamada | fila ZeroGPU | 5 min/dia conta free; 2 min anônimo | não é a key do usuário; é o Space de terceiro | Apache 2.0 | do Space, não pinado por nós |
| Modal Starter | sim | sim ("never pay for idle") | não medido neste plano para 322M | US$ 30/mês de crédito, depois pago. T4 US$ 0,000164/s | token Modal | Apache 2.0 | imagem/pin nosso |
| Groq / Cerebras / Inference Providers genérico | sim, para LLM | sim | baixo | não, e **não roda Laya** | key | n/a | n/a |

## Blocos

### A. Kaggle como inferência

Fora. Erro de categoria. A key não abre um servidor.

Também fere o uso pretendido se a conta for compartilhada. Terms (22 jun 2025): uso "internal, personal, non-commercial", "not on behalf of or for the benefit of any third party"; proibido transferir conta; proibido mais de um usuário no mesmo User ID. AUP (22 jun 2025): não permitir que terceiro use o serviço; "server farming" é abuso de recurso. Cada pessoa teria a própria key, e mesmo assim não há endpoint.

Verificação por telefone: **não está** nas páginas oficiais que li (API, Notebooks, GPU, Models, Datasets, Terms, AUP). Fontes secundárias afirmam. Não trato como fato.

### B. Kaggle só como espelho dos pesos

Viável e redundante. HF já publica os três checkpoints. Espelhar no Kaggle só vale se um dia o HF sair do ar ou a licença mudar. Não é o caminho padrão.

### C. CPU local

Continua o default. Já medido. Sem egresso. Sem cota. Lento nesta CPU (p50 1300 ms, load frio 118 s). É o fallback, não um prêmio.

### D. Modal (ou equivalente com HTTP e scale-to-zero)

Único substituto que encaixa no fluxo "apertar S e inferir" sem mentir sobre cota. O padrão já existe no `qwen-modal`: sobe no request, health-check, desce depois de minutos ociosos. Starter dá US$ 30/mês de crédito e cobra só o que corre. Não é grátis depois do crédito. Cold start de um encoder de 322–421M **não foi medido aqui**. Não prometer 33 ms na primeira chamada.

Consentimento de egresso continua obrigatório. Fallback para CPU com o motivo na tela.

### E. Space ZeroGPU oficial do Laya

Existe (`convaiinnovations/laya-demo`, "Running on Zero"). Não serve de backend. Cota free é 5 minutos de GPU por dia. SDK é Gradio. A conta que hospeda não é a do usuário. ZeroGPU pede o modelo em CUDA no import e solta a GPU no fim da função — isso é lazy de verdade, e a cota diária mata o uso de agente.

## O que não fazer

- Não tratar notebook como servidor.
- Não queimar a cota "deixando ligado por via das dúvidas".
- Não cair para OpenRouter/TypeSafe/Modal sem opt-in.
- Não publicar a key na TUI.
- Não prometer qualidade acima de ~20 opções só porque a GPU é mais rápida. O shortlist de 0.3.5 é opt-in e não foi adotado.
- Não baixar `typed-decisions` no init de quem só quer CPU.

## Lacunas

- Tempo real de fila de GPU no Kaggle: não medido.
- Cold start Modal com este peso: não medido.
- Se o fix de idioma de 0.3.5 reclassifica "Fui cobrado duas vezes": não medido. O commit deixa um caso curto sem acento de propósito no english.
- Telefone obrigatório para GPU: não confirmado na doc oficial lida.
- `kagglehub`: cache em `~/.cache/kagglehub/`, pin por versão, `force_download` para furar o cache. Se o "latest" cacheado acompanha versão nova sem `force_download`: a doc não diz. Por isso o pin é obrigatório, não opcional.

## x_search

O tool nativo `xai_x_search` não está registrado nesta sessão. `mcp describe` devolveu "not found". O que rodou foi busca web da xAI (`web_search` com provider xai, default `web_search`, não `x_search`) e posts do X via You.com. Não substitui o tool. Posts achados assim: cota flutuante acima de 30 h (staff, 2020) e, em set/2026, gente expondo endpoint dentro de notebook de TPU, com o próprio autor dizendo que não substitui servidor dedicado.

## Lane que não rodou

`researcher` e `architect` locais estão inválidos (`fallbackModels` removido). O workflow `27c962a9` falhou nos dois filhos em 0 s. A pesquisa acima é da sessão pai, com as páginas oficiais, não desses subagentes.
