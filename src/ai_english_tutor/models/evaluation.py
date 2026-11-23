# ==============================================================================
# models/evaluation.py — modelo ORM da tabela `evaluations`
# Cada linha = UMA avaliação de nível executada pelo Evaluator.
# O nível atual da sessão é a LINHA MAIS RECENTE; o histórico completo
# alimenta métricas futuras (Etapa 7 — evolução do aluno).
# ==============================================================================

# Column/Integer/String/Text/DateTime: tipos e colunas SQL
from sqlalchemy import Column, DateTime, Integer, String, Text, func

# Base: mesma base declarativa usada por Message/Correction (uma Base só)
from ai_english_tutor.models.message import Base


# Classe Evaluation — vira a tabela `evaluations` no PostgreSQL
# Herda de Base → automaticamente registrada no metadata do SQLAlchemy
class Evaluation(Base):
    """Uma avaliação de nível: qual nível, pontuação e justificativa."""

    # Nome explícito da tabela no banco de dados
    __tablename__ = "evaluations"

    # Chave primária autoincrementada (SEQUENCE do Postgres)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Sessão avaliada — permite buscar a avaliação mais recente por sessão
    # index=True → acelera o filtro ORDER BY created_at DESC do /level
    session_id = Column(String(36), nullable=False, index=True)

    # Nível resultante: beginner | basic | intermediate | advanced
    # String(20) cobre o valor mais longo ("intermediate" = 12 chars)
    level = Column(String(20), nullable=False)

    # Pontuação 0-100 usada pelo Evaluator (faixa define o nível)
    score = Column(Integer, nullable=False)

    # Justificativa breve em português (por que este nível foi decidido)
    # Text = sem limite rígido (a justificativa pode variar em tamanho)
    rationale = Column(Text, nullable=False)

    # Momento da avaliação — server_default = NOW() do banco
    # Ordenação por created_at determina qual linha é a "atual"
    created_at = Column(
        DateTime(timezone=True),           # TIMESTAMP WITH TIME ZONE
        server_default=func.now(),         # preenchido automaticamente no INSERT
        nullable=False,
    )

    # Representação em texto para debug/log
    # Ex.: <Evaluation #2 session=abc123 level=intermediate score=58>
    def __repr__(self) -> str:
        return (
            f"<Evaluation #{self.id} session={self.session_id} "
            f"level={self.level} score={self.score}>"
        )
