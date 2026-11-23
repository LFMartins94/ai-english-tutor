# ==============================================================================
# services/evaluator.py — módulo Evaluator (avaliação de nível do aluno)
# Responsabilidade única: julgar o nível de inglês do aluno a partir do
# histórico da sessão e persistir a decisão. É o ÚNICO caminho do sistema
# que altera o nível — o chat apenas lê o resultado (regra do roadmap:
# mudança de proporção PT/EN só via avaliação, nunca por tempo).
# ==============================================================================

# json: parsing da saída estruturada (JSON de nível/score/rationale)
import json

# Cliente LLM (mesmo SDK/endpoint do Tutor — Groq OpenAI-compatible)
from openai import OpenAI

# Prompt + construtor de mensagens específicos do Evaluator
from ai_english_tutor.agents.prompts import (
    DEFAULT_LEVEL,        # nível padrão de sessão sem avaliação
    LEVEL_RATIOS,         # mapa nível → proporção PT/EN válida
    build_evaluator_messages,
)

# Configurações (.env) — reutiliza URL/chave/modelo do Tutor
from ai_english_tutor.core.config import settings

# Sessão SQLAlchemy — persistência das avaliações no PostgreSQL
from sqlalchemy.orm import Session

# or_: combina filtros quando há aluno + sessão (último dos dois)
from sqlalchemy import or_

# Modelo ORM da tabela evaluations (gravação/leitura do nível)
from ai_english_tutor.models.evaluation import Evaluation

# TutorError — erros do LLM viram resposta HTTP amigável (handler global)
from ai_english_tutor.services.tutor import TutorError


# Tipo de domínio: resultado já "limpo" de uma avaliação
# (dataclass leve = só agrupa campos, sem validação pesada do pydantic)
from dataclasses import dataclass


# Estrutura imutável do resultado de uma avaliação
@dataclass
class EvaluationResult:
    """Decisão do Evaluator: nível, pontuação e justificativa."""

    # Nível resultante: uma das chaves de LEVEL_RATIOS
    level: str

    # Pontuação 0-100 (a faixa do score define o nível)
    score: int

    # Justificativa breve em português
    rationale: str


# Classe EvaluatorService — expõe evaluate() + helpers de persistência
class EvaluatorService:
    """Avalia o nível do aluno e gerencia as linhas de evaluations."""

    # Construtor: cliente próprio (julgamento pode ser mais demorado)
    def __init__(self) -> None:
        # Mesma base URL/chave do Tutor — só muda o prompt e a tarefa
        self._client = OpenAI(
            base_url=settings.LLM_BASE_URL,  # endpoint Groq
            api_key=settings.LLM_API_KEY,    # chave do .env
            timeout=45.0,                     # raciocínio longo: mais folga
            max_retries=1,                    # 1 retry basta p/ avaliação
        )

    # Método público: avalia o histórico e devolve o resultado estruturado
    def evaluate(self, history: list[dict[str, str]]) -> EvaluationResult:
        """Retorna o nível julgado pelo LLM (levanta TutorError em falha)."""

        # Sessão sem mensagens → decisão padrão, sem gastar chamada LLM
        # (não há evidência de competência para julgar)
        if not history:
            return EvaluationResult(
                level=DEFAULT_LEVEL,                      # beginner (70/30)
                score=0,                                  # sem evidência
                rationale="Sessão sem mensagens; nível inicial padrão.",
            )

        # Monta o payload [system, user-transcript] — ver agents/prompts.py
        messages = build_evaluator_messages(history)

        # Tenta a chamada ao LLM — falha vira TutorError com status certo
        try:
            response = self._client.chat.completions.create(
                model=settings.LLM_MODEL,     # 120B: julgamento exige qualidade
                messages=messages,             # critérios + transcript da sessão
                temperature=0.0,               # determinístico (avaliação fixa)
                # reasoning_effort=high: o julgamento de nível pesa gramática,
                # vocabulário e fluência — raciocínio profundo melhora o acerto
                reasoning_effort="high",
                # 4096 = folga p/ reasoning extenso + JSON final (gpt-oss
                # consome centenas de tokens "pensando" antes de responder)
                max_tokens=4096,
            )

        # Chave errada/revogada → HTTP 401 (handler global já converte)
        except Exception as exc:
            raise TutorError(
                "Não consegui avaliar o nível agora. Tente novamente.",
                status_code=502,
            ) from exc

        # Texto bruto — pode vir com ```json ... ``` em volta
        raw = response.choices[0].message.content or ""

        # Parse defensivo: extrai e valida o JSON do avaliador
        return self._parse(raw)

    # Método interno: transforma o texto do LLM em EvaluationResult
    @staticmethod
    def _parse(raw: str) -> EvaluationResult:
        """Extrai e valida o JSON da avaliação; falha vira TutorError."""

        # Limpa cercas de código (```json ... ```) que modelos às vezes emitem
        text = raw.strip()
        if text.startswith("```"):            # remove abertura de fence
            text = text.split("```", 2)[1]    # pega o miolo entre ```s
        if text.startswith("json"):           # remove tag "json" residual
            text = text[4:].strip()

        # Localiza o objeto JSON { ... } mesmo com lixo antes/depois
        start = text.find("{")                # índice do primeiro {
        end = text.rfind("}")                 # índice do último }
        if start == -1 or end == -1 or end <= start:
            raise TutorError(                 # sem JSON = resposta inválida
                "O avaliador devolveu uma resposta ilegível. Tente novamente.",
                status_code=502,
            )

        # Fatia só o trecho que parece JSON e tenta parsear
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise TutorError(                 # JSON malformado = ilegível
                "O avaliador devolveu uma resposta ilegível. Tente novamente.",
                status_code=502,
            ) from exc

        # Valida o nível: precisa ser uma das chaves de LEVEL_RATIOS
        level = data.get("level")
        if level not in LEVEL_RATIOS:
            raise TutorError(
                "O avaliador devolveu um nível desconhecido. Tente novamente.",
                status_code=502,
            )

        # Valida a pontuação: aceita int/float/string numérica, limita 0-100
        try:
            score = int(float(data.get("score", 0)))   # ex.: "58.0" → 58
        except (TypeError, ValueError):
            score = 0                                  # lixo → 0 (não quebra)
        score = max(0, min(100, score))                # clamp no intervalo

        # Justificativa: string não vazia; se faltar, usa marcador neutro
        rationale = data.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            rationale = "Sem justificativa informada pelo avaliador."

        # Tudo válido → resultado de domínio pronto para persistir
        return EvaluationResult(level=level, score=score, rationale=rationale)

    # ------------------------------------------------------------------
    # Persistência — linhas da tabela `evaluations` no PostgreSQL
    # ------------------------------------------------------------------

    @staticmethod
    def get_latest(
        db: Session,
        session_id: str | None = None,
        student_id: str | None = None,
    ) -> Evaluation | None:
        """Retorna a avaliação mais recente da sessão e/ou do aluno."""

        # Monta o filtro: com aluno, vale o MAIS RECENTE entre as
        # avaliações do perfil (qualquer sessão) e as da sessão atual
        # (sem isso, uma sessão nova perderia o nível já avaliado)
        query = db.query(Evaluation)
        if student_id and session_id:
            query = query.filter(
                or_(
                    Evaluation.student_id == student_id,   # perfil do aluno
                    Evaluation.session_id == session_id,   # sessão atual
                )
            )
        elif student_id:
            query = query.filter(Evaluation.student_id == student_id)
        else:
            query = query.filter(Evaluation.session_id == session_id)

        # ORDER BY created_at DESC + LIMIT 1 = decisão "atual"
        # created_at é server_default=NOW(); empates raros resolvidos por id
        return (
            query.order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
            .limit(1)                           # só a mais recente
            .first()
        )

    @staticmethod
    def save(
        db: Session,
        session_id: str,
        result: EvaluationResult,
        student_id: str | None = None,
    ) -> Evaluation:
        """Grava uma nova avaliação (passa a ser a atual da sessão/aluno)."""

        # Monta a linha ORM — o commit é responsabilidade do endpoint
        # (mesmo padrão do /chat: endpoint orquestra e commita uma vez)
        row = Evaluation(
            session_id=session_id,              # sessão avaliada
            student_id=student_id,              # perfil (None = anônimo)
            level=result.level,                 # nível decidido
            score=result.score,                 # pontuação 0-100
            rationale=result.rationale,         # justificativa em PT
        )
        db.add(row)                             # INSERT na transação atual
        return row


# Instância singleton — compartilhada por toda a aplicação
evaluator_service = EvaluatorService()
