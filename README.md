# Professor Carvalho — Pokémon Assistant API

API FastAPI de propósito único: um assistente conversacional especializado no universo
Pokémon, com a personalidade permanente do **Professor Carvalho** (Professor Oak).

## Sumário

- [Professor Carvalho — Pokémon Assistant API](#professor-carvalho--pokémon-assistant-api)
  - [Sumário](#sumário)
  - [Arquitetura e decisões de projeto](#arquitetura-e-decisões-de-projeto)
  - [Escolha do modelo de linguagem](#escolha-do-modelo-de-linguagem)
    - [Dois perfis de tamanho, mesmo modelo](#dois-perfis-de-tamanho-mesmo-modelo)
  - [Estratégia de personalidade e treinamento](#estratégia-de-personalidade-e-treinamento)
  - [Como rodar localmente](#como-rodar-localmente)
    - [1. Subir o modelo (Ollama)](#1-subir-o-modelo-ollama)
    - [2. Configurar e instalar a API](#2-configurar-e-instalar-a-api)
    - [3. Rodar](#3-rodar)
  - [Deploy em produção (Oracle Cloud Free Tier)](#deploy-em-produção-oracle-cloud-free-tier)
    - [1. Build e subida local (para validar antes de subir na nuvem)](#1-build-e-subida-local-para-validar-antes-de-subir-na-nuvem)
    - [2. Provisionar a instância na Oracle Cloud](#2-provisionar-a-instância-na-oracle-cloud)
    - [3. Preparar a instância](#3-preparar-a-instância)
    - [4. Subir a aplicação](#4-subir-a-aplicação)
  - [Endpoint](#endpoint)
  - [Exemplos de uso](#exemplos-de-uso)
  - [Testes](#testes)

## Arquitetura e decisões de projeto

```
prof_oak/
├── app/
│   ├── main.py                  # cria o FastAPI app, registra rotas e exception handlers
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings) via variáveis de ambiente
│   │   └── personality.py       # system prompt do Professor Carvalho (por idioma)
│   ├── models/
│   │   └── chat.py              # ChatRequest/ChatResponse/SupportedLanguage (Pydantic)
│   ├── services/
│   │   ├── llm_client.py        # wrapper assíncrono sobre um endpoint OpenAI-compatible
│   │   └── chat_service.py      # monta o prompt e orquestra a chamada ao LLM
│   └── api/
│       ├── dependencies.py      # injeção de dependência do LLMClient (singleton)
│       └── routes/
│           ├── chat.py          # POST /chat
│           └── health.py        # GET /health
├── tests/
│   └── test_chat.py
├── docker/
│   └── ollama/
│       └── Dockerfile           # imagem do Ollama com o modelo já baixado no build
├── Dockerfile                   # imagem da API
├── docker-compose.yml           # orquestra api + ollama para deploy
├── requirements.txt             # dependências de runtime
└── requirements-dev.txt         # + pytest/httpx, para desenvolvimento/testes
```

A separação `routes` → `services` → `models`/`core` existe para que a camada HTTP não
saiba nada sobre *como* o LLM é chamado, e a lógica de negócio (`chat_service`) não saiba
nada sobre FastAPI. Isso permite testar o endpoint inteiro com um `LLMClient` falso
(via `app.dependency_overrides`), sem precisar de um modelo rodando — é assim que os
testes em `tests/test_chat.py` funcionam.

**Idioma.** `language` é um `Enum` (`SupportedLanguage`) validado pelo Pydantic
diretamente no `ChatRequest`. Um valor fora de `pt-BR`/`en` já falha a validação do
FastAPI (422); um `exception_handler(RequestValidationError)` em `main.py` detecta
quando o erro é no campo `language` e devolve um corpo explícito:

```json
{
  "detail": "Idioma não suportado. / Unsupported language.",
  "supported_languages": ["pt-BR", "en"]
}
```

O idioma da resposta é **sempre** determinado pelo parâmetro `language`, nunca por
detecção automática do idioma da mensagem — a instrução é reforçada diretamente no
system prompt (ver `core/personality.py`), com prioridade máxima e uma regra explícita
de não misturar idiomas na mesma resposta.

**Cliente do LLM.** `services/llm_client.py` usa o SDK `openai` apontando para uma
`base_url` configurável, em vez de amarrar o código a um provedor específico. Isso
funciona com:
- **Ollama local** (padrão, `http://localhost:11434/v1`) — zero custo, roda na máquina
  do desenvolvedor;
- qualquer servidor OpenAI-compatible auto-hospedado (vLLM, LM Studio, text-generation-webui);
- provedores em nuvem OpenAI-compatible (Groq, Together, Fireworks) hospedando o mesmo
  modelo aberto, quando mais velocidade/escala for necessária.

Trocar de local para nuvem é uma mudança de 3 variáveis de ambiente (`LLM_BASE_URL`,
`LLM_API_KEY`, `LLM_MODEL`), sem tocar em código.

## Escolha do modelo de linguagem

| Modelo | Licença | pt-BR / en | Fine-tuning | Execução local |
|---|---|---|---|---|
| **Qwen2.5-Instruct (7B/14B)** ✅ | Apache 2.0 (sem restrições) | Excelente nos dois idiomas, um dos melhores multilíngues open-source | Ecossistema maduro (Unsloth, PEFT, Axolotl, LLaMA-Factory) | 8–16 GB RAM via Ollama/GGUF, boa velocidade |
| Llama 3.1/3.3 8B | Licença Meta (restrições de uso acima de 700M MAU, acceptable use policy) | Bom em inglês, pt-BR ok mas atrás do Qwen | Bom suporte | Similar ao Qwen |
| Mistral 7B / Nemo | Apache 2.0 | pt-BR mais fraco que Qwen | Bom | Leve, rápido |
| Gemma 2 (9B) | Licença Google (restritiva, termos de uso próprios) | Ok, mas pt-BR menos consistente | Suporte razoável | Leve |
| Kimi K2 (Moonshot) | Modified MIT, porém MoE ~1T parâmetros | Excelente | Inviável fora de datacenter | Só nuvem, custo alto |

**Escolhido: Qwen2.5-7B-Instruct** (ou `14B-instruct` se houver GPU/RAM confortável),
servido via Ollama por padrão. Critérios decisivos:

1. **Licença Apache 2.0** — sem restrições de uso comercial/acadêmico, ao contrário de
   Llama e Gemma.
2. **Qualidade em pt-BR e en simultaneamente** — requisito direto do projeto (o idioma é
   escolhido por parâmetro, então o modelo precisa ser igualmente competente nos dois).
3. **Facilidade de fine-tuning/LoRA** — caso a personalidade evolua de prompt tuning para
   fine-tuning real (ver seção seguinte), o ecossistema Qwen tem os melhores recipes
   prontos (Unsloth, LLaMA-Factory).
4. **Custo de memória/velocidade** — 7B roda confortavelmente em hardware de
   desenvolvedor comum; a mesma configuração escala para nuvem trocando só o endpoint.
5. **Kimi K2** foi descartado por não ser viável para execução local (trilhões de
   parâmetros), o que contraria o requisito de suportar "execução local ou em nuvem" de
   forma prática/barata.

### Dois perfis de tamanho, mesmo modelo

A API é pensada para dois cenários com hardware muito diferente, e ambos usam a família
Qwen2.5-Instruct — só o tamanho muda, via `LLM_MODEL`:

| Cenário | Modelo recomendado | Por quê |
|---|---|---|
| Desenvolvimento local (CPU/GPU do desenvolvedor) | `qwen2.5:7b-instruct` (padrão em `.env.example`) | Melhor qualidade de resposta; hardware não é o gargalo. |
| Deploy gratuito (Oracle Cloud Ampere A1, CPU-only, ARM) | `qwen2.5:3b-instruct` (padrão em `docker-compose.yml`) | Ver justificativa abaixo — 7B seria lento/apertado demais nesse hardware. |



## Estratégia de personalidade e treinamento

O enunciado permite três abordagens: fine-tuning, LoRA, ou prompt/personality tuning.

**Implementação atual: prompt/personality tuning.** `core/personality.py` define um
system prompt único, injetado em toda chamada, que fixa: traços de personalidade, tom,
catchphrases, escopo (só Pokémon), regra de nunca sair do personagem (exceto por
segurança/necessidade técnica) e a regra de idioma. É a abordagem correta para este
entregável porque não depende de dataset de treino, GPU dedicada ou ciclo de
fine-tuning — e modelos instruction-tuned modernos como o Qwen2.5 seguem esse tipo de
instrução de personagem de forma consistente ao longo de uma conversa.

**Evolução futura: LoRA fine-tuning.** Se for necessário fixar a personalidade de forma
ainda mais robusta (reduzir dependência do prompt, permitir prompts de sistema menores,
ou treinar em exemplos reais de diálogo do Professor Carvalho), o caminho recomendado:

1. Construir um dataset sintético de 500–2.000 pares pergunta/resposta no estilo do
   Professor Carvalho, cobrindo os tópicos do domínio (team building, EVs/IVs, cobertura
   de tipos, VGC/OU, etc.), em pt-BR e en.
2. Fine-tuning LoRA com [Unsloth](https://github.com/unslothai/unsloth) ou
   [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) sobre Qwen2.5-7B-Instruct,
   treinando apenas os adapters (baixo custo de VRAM, poucas horas em uma GPU única).
3. Servir o modelo base + adapter LoRA via Ollama (`Modelfile` com `ADAPTER`) ou vLLM
   (`--enable-lora`), mantendo a mesma interface OpenAI-compatible — nenhuma mudança no
   restante da API seria necessária.
4. Manter o system prompt mesmo após o fine-tuning, como reforço redundante de escopo e
   regra de idioma (defesa em profundidade).

## Como rodar localmente

### 1. Subir o modelo (Ollama)

```bash
# instale o Ollama: https://ollama.com/download
ollama pull qwen2.5:7b-instruct
ollama serve   # expõe http://localhost:11434/v1 (compatível com a API da OpenAI)
```

### 2. Configurar e instalar a API

```bash
cd prof_oak
python -m venv .venv
source .venv/Scripts/activate   # Windows (git bash) — use .venv\Scripts\activate no cmd
pip install -r requirements-dev.txt   # inclui pytest/httpx; use requirements.txt em produção
cp .env.example .env            # ajuste se for usar outro modelo/endpoint
```

### 3. Rodar

```bash
uvicorn app.main:app --reload
```

Documentação interativa (Swagger) em `http://localhost:8000/docs`.

## Deploy em produção (Oracle Cloud Free Tier)

O deploy usa **dois containers** via `docker-compose.yml`:

- `ollama` — construído a partir de `docker/ollama/Dockerfile`, que baixa o modelo
  **durante o build** (não no primeiro start). Isso é feito iniciando o servidor Ollama
  em segundo plano dentro do mesmo `RUN`, chamando `ollama pull`, e encerrando o
  servidor — os pesos ficam gravados na camada da imagem. Resultado: `docker compose up`
  nunca depende de internet nem espera um download antes de responder à primeira
  requisição.
- `api` — a aplicação FastAPI, que fala com o `ollama` pela rede interna do Compose
  (`http://ollama:11434/v1`); a porta 11434 nunca é exposta ao host/internet, só a 8000.

### 1. Build e subida local (para validar antes de subir na nuvem)

```bash
docker compose build   # a build do serviço `ollama` baixa ~2 GB, pode demorar alguns minutos
docker compose up -d
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Qual o melhor time para VGC?", "language": "pt-BR"}'
```

### 2. Provisionar a instância na Oracle Cloud

1. Crie uma instância **Ampere A1 (`VM.Standard.A1.Flex`)** — é a única família ARM
   coberta pelo "Always Free". Desde jun/2026 o limite gratuito total é **2 OCPU / 12 GB
   de RAM**; use tudo em uma única instância.
2. Imagem: Ubuntu (ARM64/aarch64) é a opção mais simples para instalar Docker.
3. Capacidade do Ampere A1 no tier gratuito costuma esgotar por região — se a criação
   falhar com "Out of host capacity", tente outra Availability Domain/região.
4. Adicione uma regra de **Ingress** na Security List/NSG da VCN liberando a porta
   `8000/tcp` (`0.0.0.0/0` ou restrito ao IP do seu cliente).

### 3. Preparar a instância

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER   # relogar depois disso

# o firewall interno da imagem Oracle bloqueia portas por padrão além do SSH:
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

# opcional, mas recomendado com só 12 GB de RAM: swap de segurança para o
# carregamento do modelo não disparar OOM-kill em picos de memória.
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
```

### 4. Subir a aplicação

```bash
git clone <seu-repositório> && cd prof_oak
docker compose up -d --build
```

O `docker-compose.yml` já usa `qwen2.5:3b-instruct` para ambos os serviços — combinação
validada para caber nos 2 OCPU/12 GB do Always Free. Para trocar o modelo (ex.: instância
maior, ou outra nuvem com GPU), altere `args.OLLAMA_MODEL` no serviço `ollama` **e**
`environment.LLM_MODEL` no serviço `api` no `docker-compose.yml`, depois rode
`docker compose up -d --build` novamente.

## Endpoint

`POST /chat`

```json
{
  "message": "Meu time é Charizard, Rotom-Wash, Garchomp, Ferrothorn, Dragapult e Clefable. O que posso melhorar?",
  "language": "pt-BR"
}
```

```json
{
  "response": "Olá, jovem treinador! Vejo que seu time possui uma excelente base..."
}
```

Idioma não suportado → `422`:

```json
{
  "detail": "Idioma não suportado. / Unsupported language.",
  "supported_languages": ["pt-BR", "en"]
}
```

## Exemplos de uso

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Can you help me improve my VGC team?", "language": "en"}'
```

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Qual Tera Type combina melhor com Garchomp em OU?", "language": "pt-BR"}'
```

## Testes

```bash
pytest -q
```

Os testes usam `app.dependency_overrides` para substituir o `LLMClient` real por um
fake determinístico — não é necessário ter Ollama rodando para testar a API.

