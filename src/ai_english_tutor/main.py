# ==============================================================================
# main.py — inicialização da API FastAPI e definição dos endpoints
# Camada de entrada da aplicação: recebe requisições HTTP, valida com schemas,
# delega ao service e devolve a resposta. Sem lógica de negócio pesada aqui.
# ==============================================================================

# UUID: gera identificador único universal para novas sessões de conversa
from uuid import uuid4

# FastAPI: framework que cria a app e mapeia rotas → funções Python
# Depends: marca parâmetros de função que o FastAPI deve "injetar" (DI)
# Request: objeto da requisição HTTP (usado nos handlers de erro)
# HTTPException: erro de domínio com status code (ex.: 404 sem plano)
from fastapi import Depends, FastAPI, HTTPException, Request

# Session: tipo da sessão SQLAlchemy injetada pelo endpoint via get_db()
from sqlalchemy.orm import Session

# Lifespan: contexto de vida da app (startup/shutdown) — cria tabelas ao subir
from contextlib import asynccontextmanager

# RequestValidationError: corpo/JSON inválido (campos faltando, tipo errado...)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Schemas de entrada/saída: chat, histórico, mensagens, erros e avaliação
from ai_english_tutor.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CorrectionOut,
    ErrorOut,
    ErrorsResponse,
    HistoryResponse,
    MessageOut,
)
from ai_english_tutor.schemas.evaluation import (
    EvaluateRequest,
    EvaluateResponse,
    LevelResponse,
)
from ai_english_tutor.schemas.planner import (
    PlanRequest,
    PlanResponse,
    TopicOut,
)

# Serviço do tutor (integração com o LLM) + erro de domínio TutorError
from ai_english_tutor.services.tutor import TutorError, tutor_service

# Corrector: analisa a frase do aluno e devolve erros estruturados
from ai_english_tutor.services.corrector import corrector_service

# Evaluator: julga o nível do aluno e persiste a decisão no banco
from ai_english_tutor.services.evaluator import evaluator_service

# Planner: monta o plano de aula (vocabulário/gramática/conversação)
from ai_english_tutor.services.planner import planner_service

# Funções de persistência do histórico (salvar/buscar no PostgreSQL)
from ai_english_tutor.services.history import get_history, save_message

# Relatório de erros recorrentes (agrupamento por frase errada)
from ai_english_tutor.services.errors import get_errors_summary

# Modelo ORM das correções — import registra a tabela no metadata
from ai_english_tutor.models.correction import Correction

# Modelo ORM das avaliações — import registra a tabela evaluations
from ai_english_tutor.models.evaluation import Evaluation

# Modelo ORM dos planos — import registra a tabela plans
from ai_english_tutor.models.plan import Plan

# Níveis do ensino adaptativo: proporções PT/EN e default de sessão nova
from ai_english_tutor.agents.prompts import DEFAULT_LEVEL, LEVEL_RATIOS

# Configurações carregadas do .env — usadas para expor o modelo no /health
from ai_english_tutor.core.config import settings

# Engine + sessão do banco e Base dos modelos ORM
from ai_english_tutor.core.database import get_db, engine
from ai_english_tutor.models.message import Base


# Lifespan gerencia o ciclo de vida da app:
# - startup (antes de atender): cria as tabelas se não existirem
# - shutdown (ao parar): fecha a engine (devolve conexões ao pool)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria as tabelas do banco na subida e limpa recursos na descida."""

    # CREATE TABLE IF NOT EXISTS para todas as models registradas na Base
    # Em produção usaríamos Alembic (migrations); no início, create_all basta
    Base.metadata.create_all(bind=engine)

    # yield separa startup de shutdown: tudo antes roda ao iniciar,
    # tudo depois roda quando o servidor é encerrado (Ctrl+C)
    yield

    # Dispose fecha todas as conexões do pool — encerramento limpo
    engine.dispose()


# Cria a instância da aplicação FastAPI com o lifespan definido acima
app = FastAPI(
    title="AI English Tutor API",          # título exibido em /docs
    description="Professor particular de inglês: voz, texto e ensino adaptativo",
    version="0.1.0",                       # versão inicial da API
    lifespan=lifespan,                     # hook de startup/shutdown
)


# Rota de saúde — usada por load balancers e testes de smoke
# Decorator @app.get mapeia GET /health → função abaixo
@app.get("/health")
def health() -> dict[str, str]:
    """Verifica se a API está viva e informa o modelo configurado."""

    # Dictonário retornado vira JSON automaticamente pelo FastAPI
    return {
        "status": "ok",                    # sinal de que o serviço está no ar
        "model": settings.LLM_MODEL,       # modelo LLM configurado no .env
    }


# Handler global para TutorError (falhas do LLM: auth, rate limit, timeout...)
# FastAPI procura o handler do tipo exato da exceção levantada no endpoint
@app.exception_handler(TutorError)
def tutor_error_handler(request: Request, exc: TutorError) -> JSONResponse:
    """Converte TutorError em resposta HTTP com o status code adequado."""

    # Monta o corpo do erro no padrão RFC 7807 (problem+json), simplificado:
    # o frontend lê `detail` e mostra a mensagem amigável em PT para o aluno
    return JSONResponse(
        status_code=exc.status_code,       # 401/429/502/504 conforme o caso
        content={"detail": str(exc)},      # mensagem humanizada do TutorError
    )


# Handler para JSON malformado ou campos inválidos no request (422)
# Retorna 400 com lista de erros legível em vez do payload padrão do FastAPI
@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Traduz erros de validação pydantic em mensagem simples para o aluno."""

    # errors() devolve a lista de campos com problema (campo, tipo, msg...)
    # Concatenamos só as mensagens em PT para facilitar o entendimento
    messages = "; ".join(
        f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    )

    # Devolve 400 (bad request) com o resumo dos erros de validação
    return JSONResponse(
        status_code=400,
        content={"detail": f"Requisição inválida — {messages}"},
    )


# Rota principal do chat — recebe a mensagem do aluno e devolve a resposta
# Decorator @app.post mapeia POST /chat e valida o corpo com ChatRequest
# O FastAPI injeta um ChatRequest já validado no parâmetro `payload`
@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,                          # corpo JSON já validado
    db: Session = Depends(get_db),                 # sessão do banco injetada
) -> ChatResponse:
    """Conversa com o tutor, persiste o turno no banco e devolve a resposta."""

    # Gera um novo UUID se o cliente não enviou session_id (conversa nova)
    # uuid4() → ex.: "3f8a2c1e-..." (36 chars) — único globalmente
    session_id = payload.session_id or str(uuid4())

    # Recupera do banco as mensagens anteriores desta sessão (fonte oficial)
    prior_messages = get_history(db, session_id)

    # Converte as linhas do banco no formato [{"role", "content"}, ...]
    # que o serviço do tutor/LLM entende — list comprehension sobre os objs
    db_history = [
        {"role": m.role, "content": m.content}   # mapeia colunas → dicts
        for m in prior_messages                   # para cada mensagem salva
    ]

    # Fallback: se o banco ainda não tem nada, usa o history do frontend
    # (mantém compatibilidade com clientes que mandam o contexto antigo)
    history_for_llm = db_history if db_history else (payload.history or [])

    # Nível ATUAL da sessão: última avaliação do Evaluator, ou o default.
    # O chat apenas LÊ o nível — alterá-lo exige POST /evaluate (regra do
    # roadmap: mudança de proporção PT/EN só via avaliação, nunca por tempo)
    latest_evaluation = evaluator_service.get_latest(db, session_id)
    current_level = latest_evaluation.level if latest_evaluation else DEFAULT_LEVEL

    # Foco da aula: plano VIGENTE da sessão, se existir (gerado pelo
    # Planner via POST /plan). O chat apenas LÊ — gerar plano é o Planner
    current_plan = planner_service.get_latest(db, session_id)
    lesson_focus = current_plan.focus if current_plan else None

    # Delega a geração da resposta ao serviço (integração com o LLM)
    # Falhas do LLM levantam TutorError — capturada pelo handler global
    reply_text = tutor_service.reply(
        user_message=payload.message,       # texto novo do aluno
        history=history_for_llm,            # contexto: banco (ou fallback)
        level=current_level,                # proporção PT/EN da sessão
        lesson_focus=lesson_focus,          # foco do plano (se houver)
    )

    # Persiste o turno completo: mensagem do aluno E resposta do tutor
    # Na ordem cronológica — o GET /history devolve como foi gravado
    save_message(db, session_id, "user", payload.message)        # fala do aluno
    save_message(db, session_id, "assistant", reply_text)        # fala do tutor

    # Corrector: audita a frase do aluno (2ª chamada LLM, barata e curta)
    # Devolve [] se falhar — degradação graceful, o chat não quebra
    correction_items = corrector_service.analyze(payload.message)

    # Persiste cada erro detectado na tabela corrections (para recorrência)
    for item in correction_items:
        db.add(
            Correction(                 # linha nova na tabela corrections
                session_id=session_id,  # mesma sessão da conversa
                wrong=item.wrong,       # frase errada do aluno
                correct=item.correct,   # versão corrigida
                explanation=item.explanation,  # explicação em PT
            )
        )
    # COMMIT ÚNICO para todas as correções do turno (mais eficiente que
    # um commit por item — uma transação atômica para o lote inteiro)
    db.commit()

    # Converte CorrectionItem (domínio) → CorrectionOut (schema de saída)
    corrections_out = [
        CorrectionOut(
            wrong=item.wrong,               # frase errada
            correct=item.correct,           # versão corrigida
            explanation=item.explanation,   # explicação em PT
        )
        for item in correction_items        # para cada erro detectado
    ]

    # Monta o schema de saída — o FastAPI serializa em JSON na resposta
    return ChatResponse(
        reply=reply_text,                   # resposta gerada pelo tutor
        model=settings.LLM_MODEL,           # qual modelo produziu a resposta
        session_id=session_id,              # cliente reenvia este id no próximo turno
        corrections=corrections_out,        # erros do turno (pode ser [])
    )


# Rota de histórico — devolve todas as mensagens de uma sessão
# Decorator @app.get mapeia GET /history/{session_id} com parâmetro de caminho
@app.get("/history/{session_id}", response_model=HistoryResponse)
def history(
    session_id: str,                               # id vindo da URL
    db: Session = Depends(get_db),                 # sessão do banco injetada
) -> HistoryResponse:
    """Recupera a conversa completa de uma sessão do PostgreSQL."""

    # Busca as mensagens ordenadas cronologicamente (limit 100)
    rows = get_history(db, session_id)

    # Converte cada linha ORM Message → schema MessageOut (serialização)
    # created_at.isoformat() transforma datetime em string ISO 8601 p/ JSON
    messages = [
        MessageOut(
            role=row.role,                  # "user" ou "assistant"
            content=row.content,            # texto da mensagem
            created_at=row.created_at.isoformat(),  # datetime → "2026-..." 
        )
        for row in rows                     # itera sobre as linhas do banco
    ]

    # Devolve o envelope completo: id da sessão + lista de mensagens
    return HistoryResponse(
        session_id=session_id,              # ecoa o id consultado
        messages=messages,                  # conversa em ordem cronológica
    )


# Rota de erros recorrentes — agrupa corrections por frase errada
# Ordena dos mais frequentes: base do relatório "o que você mais erra"
@app.get("/errors/{session_id}", response_model=ErrorsResponse)
def errors(
    session_id: str,                               # id vindo da URL
    db: Session = Depends(get_db),                 # sessão do banco injetada
) -> ErrorsResponse:
    """Lista os erros de inglês da sessão, dos mais para os menos frequentes."""

    # Agrega no banco: GROUP BY wrong + COUNT(*) ORDER BY count DESC
    summaries = get_errors_summary(db, session_id)

    # Converte ErrorSummary (domínio) → ErrorOut (schema de saída)
    errors_out = [
        ErrorOut(
            wrong=e.wrong,                 # frase errada agrupada
            correct=e.correct,             # correção correspondente
            explanation=e.explanation,     # explicação em PT
            count=e.count,                 # frequência na sessão
        )
        for e in summaries                 # itera sobre os grupos
    ]

    # Envelope: id da sessão + lista de erros ordenada
    return ErrorsResponse(
        session_id=session_id,             # ecoa o id consultado
        errors=errors_out,                 # recorrentes primeiro
    )


# Rota de avaliação — ÚNICO caminho que altera o nível da sessão
# Decorator @app.post mapeia POST /evaluate e valida com EvaluateRequest
@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    payload: EvaluateRequest,                        # corpo JSON validado
    db: Session = Depends(get_db),                   # sessão do banco
) -> EvaluateResponse:
    """Avalia o nível do aluno pelo histórico e grava a decisão."""

    # Busca o histórico da sessão (fonte oficial de evidências)
    rows = get_history(db, payload.session_id)

    # Converte linhas ORM → [{"role","content"}, ...] p/ o Evaluator
    history_dicts = [
        {"role": row.role, "content": row.content}   # mapeia colunas → dicts
        for row in rows                              # para cada mensagem
    ]

    # Delega o julgamento ao serviço (2ª chamada LLM, só na avaliação)
    # Falhas do LLM/JSON levantam TutorError → handler global converte
    result = evaluator_service.evaluate(history_dicts)

    # Persiste a nova avaliação — passa a ser a ATUAL da sessão
    # (o histórico de linhas alimenta métricas da Etapa 7)
    evaluator_service.save(db, payload.session_id, result)

    # COMMIT ÚNICO da transação (mesmo padrão do /chat)
    db.commit()

    # Envelope: decisão + proporção PT/EN que passa a valer no chat
    return EvaluateResponse(
        session_id=payload.session_id,         # ecoa a sessão avaliada
        level=result.level,                    # nível decidido
        score=result.score,                    # pontuação 0-100
        rationale=result.rationale,            # justificativa em PT
        pt_en_ratio=LEVEL_RATIOS[result.level],  # ex.: "70/30"
    )


# Rota do nível atual — apenas LEITURA, nunca altera nada
# Decorator @app.get mapeia GET /level/{session_id} com parâmetro de caminho
@app.get("/level/{session_id}", response_model=LevelResponse)
def level(
    session_id: str,                               # id vindo da URL
    db: Session = Depends(get_db),                 # sessão do banco injetada
) -> LevelResponse:
    """Devolve o nível vigente da sessão (default beginner se nunca avaliada)."""

    # Última avaliação gravada (None = sessão nunca avaliada)
    latest = evaluator_service.get_latest(db, session_id)

    # Sem avaliação → default do sistema (beginner, 70/30)
    # Com avaliação → linha mais recente determina o nível atual
    current_level = latest.level if latest else DEFAULT_LEVEL

    # Envelope com o nível, a proporção e se já houve avaliação formal
    return LevelResponse(
        session_id=session_id,                     # ecoa o id consultado
        level=current_level,                       # nível vigente
        pt_en_ratio=LEVEL_RATIOS[current_level],   # ex.: "70/30"
        evaluated=latest is not None,              # true = já foi avaliada
    )


# Rota de plano de aula — gera o próximo plano para a sessão
# Decorator @app.post mapeia POST /plan e valida com PlanRequest
@app.post("/plan", response_model=PlanResponse)
def plan(
    payload: PlanRequest,                          # corpo JSON validado
    db: Session = Depends(get_db),                 # sessão do banco
) -> PlanResponse:
    """Gera plano progressivo (vocab/gramática/conversa) para a sessão."""

    # Nível ATUAL: lido do Evaluator (integração plano ↔ nível do roadmap)
    latest_evaluation = evaluator_service.get_latest(db, payload.session_id)
    current_level = latest_evaluation.level if latest_evaluation else DEFAULT_LEVEL

    # Tópicos já planejados antes — o Planner NÃO pode repetir nenhum
    # (é isso que garante a progressão entre planos da mesma sessão)
    covered_topics = planner_service.get_covered_topics(db, payload.session_id)

    # Histórico da sessão — dá contexto sobre o que o aluno já pratica
    rows = get_history(db, payload.session_id)
    history_dicts = [
        {"role": row.role, "content": row.content}   # mapeia colunas → dicts
        for row in rows                              # para cada mensagem
    ]

    # Delega o planejamento ao serviço (2ª chamada LLM, só no /plan)
    # Falhas do LLM/JSON levantam TutorError → handler global converte
    result = planner_service.generate(current_level, history_dicts, covered_topics)

    # Persiste o novo plano — passa a ser o VIGENTE da sessão
    planner_service.save(db, payload.session_id, current_level, result)

    # COMMIT ÚNICO da transação (mesmo padrão do /chat e /evaluate)
    db.commit()

    # Converte TopicItem (domínio) → TopicOut (schema de saída)
    topics_out = [
        TopicOut(kind=t.kind, title=t.title, detail=t.detail)   # tópico
        for t in result.topics                                  # para cada um
    ]

    # Envelope: plano + nível/proporção em que foi gerado
    return PlanResponse(
        session_id=payload.session_id,           # ecoa a sessão do plano
        level=current_level,                     # nível considerado
        pt_en_ratio=LEVEL_RATIOS[current_level], # ex.: "70/30"
        focus=result.focus,                      # objetivo da aula
        topics=topics_out,                       # 3 tópicos na ordem
        rationale=result.rationale,              # justificativa em PT
    )


# Rota do plano vigente — apenas LEITURA, nunca altera nada
# Decorator @app.get mapeia GET /plan/{session_id} com parâmetro de caminho
@app.get("/plan/{session_id}", response_model=PlanResponse)
def get_plan(
    session_id: str,                             # id vindo da URL
    db: Session = Depends(get_db),               # sessão do banco injetada
) -> PlanResponse:
    """Devolve o plano de aula vigente da sessão (404 se nunca gerado)."""

    # Último plano gravado (None = sessão nunca teve plano)
    latest = planner_service.get_latest(db, session_id)

    # Sem plano → 404 com mensagem clara em PT (não existe plano ainda)
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail="Nenhum plano gerado para esta sessão. Use POST /plan.",
        )

    # Converte a linha ORM → schema PlanResponse (serialização)
    topics_out = [
        TopicOut(
            kind=str(t.get("kind", "")),        # vocabulary|grammar|conversation
            title=str(t.get("title", "")),      # título curto
            detail=str(t.get("detail", "")),    # orientação em PT
        )
        for t in latest.topics or []            # topics já vem como list[dict]
    ]

    # Envelope com o plano vigente + proporção do nível em que foi gerado
    return PlanResponse(
        session_id=session_id,                    # ecoa o id consultado
        level=latest.level,                       # nível na época do plano
        pt_en_ratio=LEVEL_RATIOS.get(latest.level, LEVEL_RATIOS[DEFAULT_LEVEL]),
        focus=latest.focus,                       # objetivo da aula
        topics=topics_out,                        # 3 tópicos na ordem
        rationale=latest.rationale,               # justificativa em PT
    )


# Ponto de entrada para rodar localmente com `python -m ai_english_tutor.main`
# uvicorn.run sobe o servidor ASGI na porta 8000 em modo reload (dev)
def main() -> None:
    """Sobe o servidor de desenvolvimento da API."""

    # Import tardio do uvicorn: evita custo de import se o módulo só for importado
    import uvicorn

    # host 0.0.0.0 = aceita conexões externas (docker/rede); port 8000 = padrão
    # reload=True = reinicia ao salvar arquivos (apenas em desenvolvimento)
    uvicorn.run(
        "ai_english_tutor.main:app",        # caminho da app no formato app:obj
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


# Guarda padrão: só executa main() quando o arquivo roda como script
# (quando importado como módulo, o bloco é ignorado)
if __name__ == "__main__":
    main()
