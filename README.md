# AI English Tutor

Professor particular de inglês inteligente: conversa por voz e texto, ensino adaptativo e memória de longo prazo.

Projeto em desenvolvimento — conduzido como um projeto de Engenharia de IA: primeiro a arquitetura, depois cada componente em Python, testes e evolução do sistema.

---

## Índice

1. [Objetivo](#1-objetivo)
2. [Como o professor ensina](#2-como-o-professor-ensina)
3. [Arquitetura do sistema](#3-arquitetura-do-sistema)
4. [Responsabilidade de cada componente](#4-responsabilidade-de-cada-componente)
5. [Tecnologias e suas funções](#5-tecnologias-e-suas-funções)
6. [Estrutura de pastas](#6-estrutura-de-pastas)
7. [Roadmap de etapas](#7-roadmap-de-etapas)
8. [Setup e execução](#8-setup-e-execução)
9. [Endpoints da API](#9-endpoints-da-api)

---

## 1. Objetivo

| Característica | Definição |
|---|---|
| Nível inicial | Básico |
| Método | Imersão progressiva |
| Idiomas | Português e inglês |
| Comunicação | Voz e texto |
| Backend | Python + FastAPI |
| LLM | Modelo de linguagem via API (Groq — `openai/gpt-oss-120b`) |
| Banco de dados | PostgreSQL |
| Orquestração futura | LangGraph |
| Comunicação por voz | STT + TTS / tempo real |
| Interface | Aplicação web |

---

## 2. Como o professor ensina

A **imersão progressiva** é a característica central. A proporção de português e inglês muda conforme a evolução do aluno:

| Etapa | Idioma utilizado |
|---|---|
| Inicial | 70% português / 30% inglês |
| Básico evoluindo | 50% português / 50% inglês |
| Intermediário | 20% português / 80% inglês |
| Avançado | 100% inglês, com exceções pedagógicas |

Essas proporções são ajustáveis conforme o desempenho. **Não mudamos de nível com o passar dos dias**: o agente avalia se o aluno realmente está preparado antes de avançar.

---

## 3. Arquitetura do sistema

Começamos com uma arquitetura modular, preparada para crescer — sem vários agentes autônomos, LangGraph, RAG e dezenas de ferramentas no início. Primeiro construímos um agente funcional; depois adicionamos inteligência, memória e especialização.

```
┌─────────────────────────────────────────────┐
│           INTERFACE DO ALUNO                │
│     Texto │ Microfone │ Áudio │ Histórico   │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│            FASTAPI — BACKEND                │
│   Recebe requisições e gerencia sessões     │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│           AI ENGLISH TUTOR                  │
│         Motor central de inteligência       │
│                                             │
│   ┌────────┐ ┌──────────┐ ┌───────────┐     │
│   │ Tutor  │ │Corrector │ │ Evaluator │     │
│   └────────┘ └──────────┘ └───────────┘     │
│   ┌────────┐ ┌────────┐ ┌────────────┐      │
│   │ Planner│ │ Memory │ │   Voice    │      │
│   └────────┘ └────────┘ └────────────┘      │
└──────────┬───────────────────┬──────────────┘
           │                   │
           ▼                   ▼
┌──────────────────┐  ┌──────────────────────┐
│   PostgreSQL     │  │   Motor de voz       │
│ Histórico e      │  │   STT, TTS e áudio   │
│ progresso        │  │                      │
└──────────────────┘  └──────────────────────┘
```

**Distinção importante:** inicialmente Tutor, Corrector, Evaluator e Planner são **módulos lógicos dentro de uma mesma aplicação**, não quatro agentes independentes. Isso facilita testes, manutenção e controle de custos.

---

## 4. Responsabilidade de cada componente

| Componente | Responsabilidade |
|---|---|
| **Tutor** | Conduz conversas e ensina |
| **Corrector** | Identifica e explica erros |
| **Evaluator** | Avalia o nível e a evolução do aluno |
| **Planner** | Seleciona conteúdos e exercícios |
| **Memory** | Recupera o histórico de aprendizagem |
| **Voice** | Converte fala em texto e texto em fala (STT/TTS) |

Separação de responsabilidades no código:

- `agents/prompts.py` — define **como** o professor pensa e se comporta.
- `services/tutor.py` — implementa a **comunicação** com o modelo de IA.
- `main.py` — **recebe** as solicitações e **entrega** as respostas.

---

## 5. Tecnologias e suas funções

| Tecnologia | Função |
|---|---|
| **Python** | Linguagem principal: lógica e processamento |
| **FastAPI** | Construção dos endpoints e comunicação com a interface |
| **API de LLM (Groq)** | Compreensão, geração de respostas e correções |
| **PostgreSQL** | Persistência de conversas, vocabulário e desempenho |
| **LangGraph** | Orquestração de fluxos mais complexos (etapa futura) |

### Modalidades de voz

- **Modo convencional** (inicial): STT transcreve o áudio → LLM responde → TTS gera a fala.
- **Modo em tempo real** (futuro): conexão de áudio bidirecional, conversas mais naturais e com menor latência.

Começamos pelo modo convencional, que é mais simples de implementar e depurar.

---

## 6. Estrutura de pastas

```
ai-english-tutor/
│
├── src/
│   └── ai_english_tutor/
│       ├── __init__.py          # raiz do pacote
│       ├── main.py              # inicialização da API e endpoints
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py        # configurações e variáveis de ambiente
│       │   └── database.py      # engine + sessão do PostgreSQL
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   └── prompts.py       # instruções e comportamento dos módulos
│       │
│       ├── models/              # mapeamento tabela ↔ classe (ORM)
│       │   ├── message.py       # tabela messages
│       │   ├── correction.py    # tabela corrections
│       │   ├── evaluation.py    # tabela evaluations
│       │   ├── plan.py          # tabela plans
│       │   ├── student.py       # tabela students (perfil)
│       │   └── student_word.py  # tabela student_words (vocab/erros)
│       │
│       ├── services/
│       │   ├── tutor.py         # conversa com o LLM
│       │   ├── corrector.py     # análise de erros do aluno
│       │   ├── evaluator.py     # avaliação de nível
│       │   ├── planner.py       # plano de aula progressivo
│       │   ├── students.py      # memória de longo prazo do aluno
│       │   ├── voice.py         # voz: transcrição (Whisper) e síntese (Orpheus)
│       │   ├── history.py       # persistência do histórico
│       │   └── errors.py        # erros recorrentes
│       │
│       └── schemas/             # modelos de entrada e saída
│           ├── chat.py
│           ├── evaluation.py
│           ├── planner.py
│           ├── student.py
│           └── voice.py
│
├── .env                         # segredos locais (não versionado)
├── .env.example                 # template das variáveis de ambiente
├── .gitignore
├── pyproject.toml               # metadados e dependências (uv)
├── FALTANDO.md                  # roadmap de etapas
└── README.md
```

| Pasta / arquivo | Responsabilidade |
|---|---|
| `core/` | Configurações e variáveis de ambiente |
| `agents/` | Instruções e comportamento dos agentes |
| `services/` | Lógica de negócio e integração com o LLM |
| `schemas/` | Modelos de entrada e saída |
| `main.py` | Inicialização da API e endpoints |

---

## 7. Roadmap de etapas

O andamento completo está em [`FALTANDO.md`](FALTANDO.md).

| # | Etapa | Status |
|---|---|---|
| 1 | Base do projeto (estrutura, config, health check) | ✅ Concluída |
| 2 | Chat de texto ponta-a-ponta com LLM | ✅ Concluída |
| 3 | Persistência no PostgreSQL (histórico) | ✅ Concluída |
| 4 | Corrector (correções integradas) | ✅ Concluída |
| 5 | Evaluator (nível + proporção PT/EN adaptativa) | ✅ Concluída |
| 6 | Planner (conteúdos e exercícios) | ✅ Concluída |
| 7 | Memory (perfil e evolução de longo prazo) | ✅ Concluída |
| 8 | Voz — modo convencional (STT + TTS) | ✅ Concluída |
| 9 | Interface web | ⬜ Pendente |
| 10 | LangGraph + voz em tempo real (futuro) | ⬜ Pendente |

---

## 8. Setup e execução

### Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (gerenciador de dependências e ambiente virtual)
- Python ≥ 3.14 (o uv baixa automaticamente conforme `.python-version`)
- Chave de API da [Groq](https://console.groq.com/keys)

### Instalação

```bash
# 1. Clona o repositório
git clone <repo-url>
cd ai-english-tutor

# 2. Instala dependências e cria o ambiente virtual
uv sync

# 3. Cria o arquivo de ambiente a partir do template
copy .env.example .env    # Windows
# cp .env.example .env    # macOS/Linux

# 4. Edite .env e cole sua chave real da Groq
#    LLM_API_KEY=gsk_...
```

### Execução

```bash
# Sobe a API em http://127.0.0.1:8000 (com reload automático)
uv run ai-english-tutor
```

### Verificação

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","model":"openai/gpt-oss-120b"}
```

Documentação interativa gerada pelo FastAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 9. Endpoints da API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Health check: status e modelo configurado |
| `POST` | `/chat` | Recebe `{message, session_id?}` e devolve `{reply, model, session_id, corrections}` |
| `GET` | `/history/{session_id}` | Histórico completo da sessão (mensagens em ordem cronológica) |
| `GET` | `/errors/{session_id}` | Erros recorrentes do aluno, ordenados por frequência |
| `POST` | `/evaluate` | Avalia o nível da sessão (único caminho que altera o nível) |
| `GET` | `/level/{session_id}` | Nível atual da sessão + proporção PT/EN (leitura pura) |
| `POST` | `/plan` | Gera o plano da aula (vocabulário, gramática, conversação) |
| `GET` | `/plan/{session_id}` | Plano de aula vigente da sessão (404 se nunca gerado) |
| `POST` | `/students` | Cadastra o aluno (perfil de memória de longo prazo) |
| `GET` | `/students/{student_id}` | Perfil do aluno (404 se não cadastrado) |
| `POST` | `/students/{student_id}/words` | Registra vocabulário ou erro (dedupe) |
| `GET` | `/students/{student_id}/words` | Palavras do aluno (`?kind=vocabulary\|mistake`) |
| `GET` | `/students/{student_id}/metrics` | Métricas: sessões, correções, curva de avaliações |
| `GET` | `/students/{student_id}/context` | Memória pronta para conversas novas |
| `POST` | `/transcribe` | Upload de áudio (multipart) → texto falado (Whisper) |
| `POST` | `/speak` | `{text, voice?}` → arquivo WAV com a fala (Orpheus) |

Os endpoints `POST /chat`, `POST /evaluate` e `POST /plan` aceitam
`student_id` opcional no corpo: com ele, nível, plano e erros passam a
valer em **todas** as sessões do aluno (memória entre conversas).

### Exemplo de chamada

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Olá! Me ensine a me apresentar em inglês."}'
```

```json
{
  "reply": "Olá! Vamos começar... Hello, my name is...",
  "model": "openai/gpt-oss-120b"
}
```
