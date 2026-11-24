# FALTANDO.md — Roadmap do AI English Tutor

Andamento do projeto. Marque cada etapa como ✅ quando concluída e verificada.

**Legenda:** ✅ Concluída · 🔄 Em andamento · ⬜ Pendente

---

## Etapa 1 — Base do projeto ✅

- [x] Estrutura de pastas (`core/`, `agents/`, `services/`, `schemas/`)
- [x] Configurações via `pydantic-settings` + `.env` / `.env.example`
- [x] Dependências no `pyproject.toml` (fastapi, uvicorn, openai, pydantic-settings)
- [x] Health check `GET /health`
- [x] Endpoint `POST /chat` (estrutura pronta — integração LLM validada na Etapa 2)
- [x] Verificação: `uv sync` + API no ar + `/health` respondendo 200

---

## Etapa 2 — Chat de texto ponta-a-ponta ✅

- [x] `.env` real com chave da Groq
- [x] Testar `POST /chat` com o modelo `openai/gpt-oss-120b`
- [x] Validar persona do tutor (imersão progressiva) nas respostas
- [x] Tratamento de erros da API (timeout, rate limit, chave inválida)
- [x] Verificação: turnos 1 e 2 com histórico (200), validação 400, `/health` 200

---

## Etapa 3 — Persistência no PostgreSQL ✅

- [x] Instância/DB PostgreSQL + driver (SQLAlchemy + psycopg v3, container Docker)
- [x] Tabela de mensagens (`messages`: session_id, role, content, created_at)
- [x] Endpoint de histórico (`GET /history/{session_id}`)
- [x] Histórico guardado no servidor (POST /chat grava user + assistant)
- [x] Verificação: 2 turnos → 4 linhas no psql; history 200; sessão vazia 200; validação 400

---

## Etapa 4 — Corrector ✅

- [x] Módulo lógico de correção integrado ao fluxo do chat (2ª chamada LLM)
- [x] Formato de correção: frase errada → explicação → versão correta (JSON estruturado)
- [x] Registro de erros recorrentes por aluno (`GET /errors/{session_id}` com contagem)
- [x] Tabela `corrections` persistida no PostgreSQL
- [x] Verificação: turnos com erros → corrections no response; recorrência count=2; PT sem erros → []; psql OK
- [x] Bug corrigido: `max_tokens` insuficiente p/ reasoning do gpt-oss-120b (500 → 2048)

---

## Etapa 5 — Evaluator ✅

- [x] Avaliação de nível (diagnóstico inicial + reavaliações)
- [x] Regra: mudança de proporção PT/EN só após avaliação, nunca por tempo
- [x] Ajuste dinâmico do system prompt conforme o nível atual
- [x] Tabela `evaluations` (log de decisões — base das métricas da Etapa 7)
- [x] Verificação: sessão nova → beginner 70/30; conversa avançada → advanced (85);
  só PT → beginner (5); última avaliação prevalece; chat não altera nível; 9/9 testes

---

## Etapa 6 — Planner ✅

- [x] Seleção de conteúdos e exercícios por nível (vocabulary/grammar/conversation)
- [x] Plano de aula progressivo — não repete tópicos já cobertos
- [x] Integração com Evaluator: plano usa o nível vigente da sessão
- [x] Tabela `plans` + `POST /plan` / `GET /plan/{session_id}`
- [x] Chat recebe o foco do plano vigente (CURRENT LESSON FOCUS no prompt)
- [x] Verificação: beginner → "Cores/to be/Apresentação"; advanced → "Idioms/
  Mixed Conditionals/Debate"; 2º plano sem repetição; chat usa foco; 9/9 testes

---

## Etapa 7 — Memory (longo prazo) ✅

- [x] Perfil do aluno (`students`: id, objetivos, idioma nativo) — `POST/GET /students`
- [x] Vocabulário estudado / palavras erradas (`student_words` + dedupe;
      erros do Corrector entram automático no perfil com `student_id`)
- [x] Histórico de evolução e métricas (`GET /students/{id}/metrics`:
      sessões, mensagens, correções, curva de avaliações)
- [x] Recuperação de contexto em novas sessões (`GET /students/{id}/context`
      + chat com `student_id` herda nível/foco/erros entre sessões)
- [x] `student_id` vincula messages/corrections/evaluations/plans (ALTER + índices)
- [x] Verificação: nível avaliado na sessão A vale na B; erros capturados
      do chat; progressão de planos entre sessões; anônimo continua ok; 13/13 testes

---

## Etapa 8 — Voz: modo convencional ✅

- [x] STT: `POST /transcribe` (upload multipart → Whisper large v3 turbo)
- [x] TTS: `POST /speak` (texto/voz → WAV Orpheus; fatia em blocos de 190 chars
      por causa do limite de 200 chars do modelo e remonta um WAV só)
- [x] Header WAV normalizado (Groq envia tamanhos de streaming 0xFFFFFFFF)
- [x] Validações: áudio vazio/grande, texto vazio, voz inválida, sem arquivo
- [x] Erro amigável quando o modelo de voz precisa de aceite de termos no console
- [x] Fluxo completo: falar → transcrever → LLM → sintetizar; 13/13 testes

---

## Etapa 9 — Interface web ⬜

- [ ] Frontend de chat (texto)
- [ ] Botão de microfone + player de áudio
- [ ] Exibição de correções e progresso do aluno

---

## Etapa 10 — Futuro: LangGraph + voz em tempo real ⬜

- [ ] Orquestração dos módulos com LangGraph (fluxos complexos)
- [ ] Modo tempo real: áudio bidirecional com baixa latência
- [ ] Possíveis agentes especializados separados (se fizer sentido)

---

*Última atualização: Etapa 8 concluída.*
