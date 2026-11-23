# ==============================================================================
# models/plan.py — modelo ORM da tabela `plans`
# Cada linha = UMA geração de plano de aula para uma sessão.
# O plano vigente é a LINHA MAIS RECENTE; o histórico de planos garante
# progressão (o Planner recebe os tópicos já cobertos e não repete).
# ==============================================================================

# Column/Integer/String/Text/JSON/DateTime: tipos e colunas SQL
from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func

# Base: mesma base declarativa usada por Message/Correction/Evaluation
from ai_english_tutor.models.message import Base


# Classe Plan — vira a tabela `plans` no PostgreSQL
# Herda de Base → automaticamente registrada no metadata do SQLAlchemy
class Plan(Base):
    """Um plano de aula: foco, 3 tópicos e justificativa para a sessão."""

    # Nome explícito da tabela no banco de dados
    __tablename__ = "plans"

    # Chave primária autoincrementada (SEQUENCE do Postgres)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Sessão do plano — permite buscar o plano mais recente por sessão
    # index=True → acelera o filtro ORDER BY created_at DESC do /plan
    session_id = Column(String(36), nullable=False, index=True)

    # Nível do aluno NO MOMENTO da geração (vem do Evaluator)
    # Guardar junto permite auditar planos por nível sem join
    level = Column(String(20), nullable=False)

    # Objetivo da aula em uma frase (injetado no system prompt do chat)
    focus = Column(Text, nullable=False)

    # Lista JSON de tópicos: [{"kind","title","detail"}, ...]
    # JSON do SQLAlchemy serializa/deserializa sozinho (JSON/JSONB no PG)
    topics = Column(JSON, nullable=False)

    # Justificativa breve em português (por que estes tópicos, este nível)
    rationale = Column(Text, nullable=False)

    # Momento da geração — server_default = NOW() do banco
    # Ordenação por created_at determina qual linha é o "plano atual"
    created_at = Column(
        DateTime(timezone=True),           # TIMESTAMP WITH TIME ZONE
        server_default=func.now(),         # preenchido automaticamente no INSERT
        nullable=False,
    )

    # Representação em texto para debug/log
    # Ex.: <Plan #2 session=abc123 level=basic focus='Daily routine...'>
    def __repr__(self) -> str:
        return (
            f"<Plan #{self.id} session={self.session_id} "
            f"level={self.level} focus={self.focus[:30]!r}>"
        )
