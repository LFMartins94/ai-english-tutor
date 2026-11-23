# ==============================================================================
# models/correction.py — modelo ORM da tabela `corrections`
# Cada linha = UM erro do aluno detectado pelo Corrector numa sessão.
# Alimenta o relatório de erros recorrentes (GET /errors/{session_id}).
# ==============================================================================

# Column/Integer/String/Text/DateTime: tipos e colunas SQL
from sqlalchemy import Column, DateTime, Integer, String, Text, func

# Base: mesma base declarativa usada por Message (uma Base por aplicação)
from ai_english_tutor.models.message import Base


# Classe Correction — vira a tabela `corrections` no PostgreSQL
# Herda de Base → automaticamente registrada no metadata do SQLAlchemy
class Correction(Base):
    """Um erro detectado na mensagem do aluno (frase errada → versão correta)."""

    # Nome explícito da tabela no banco de dados
    __tablename__ = "corrections"

    # Chave primária autoincrementada (SEQUENCE do Postgres)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Sessão onde o erro aconteceu — permite agrupar erros por conversa
    # index=True → acelera o filtro do GET /errors/{session_id}
    session_id = Column(String(36), nullable=False, index=True)

    # Trecho incorreto escrito pelo aluno (ex.: "I am agree")
    # String(500) = suficiente para qualquer frase curta citada
    wrong = Column(String(500), nullable=False)

    # Versão corrigida pelo tutor (ex.: "I agree")
    correct = Column(String(500), nullable=False)

    # Explicação breve em português (por que estava errado)
    # Text = sem limite rígido de tamanho (explicações podem ser longas)
    explanation = Column(Text, nullable=False)

    # Momento da detecção — server_default = NOW() do banco
    created_at = Column(
        DateTime(timezone=True),           # TIMESTAMP WITH TIME ZONE
        server_default=func.now(),         # preenchido automaticamente no INSERT
        nullable=False,
    )

    # Representação em texto para debug/log
    # Ex.: <Correction #3 session=abc123 wrong='I am agree'>
    def __repr__(self) -> str:
        return (
            f"<Correction #{self.id} session={self.session_id} "
            f"wrong={self.wrong!r}>"
        )
