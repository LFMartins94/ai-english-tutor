# ==============================================================================
# models/student_word.py — modelo ORM da tabela `student_words`
# Cada linha = UMA palavra/frase registrada no perfil do aluno:
# kind="vocabulary" → vocabulário estudado; kind="mistake" → erro recorrente.
# Alimenta o relatório de evolução e o contexto recuperado em novas sessões.
# ==============================================================================

# Column/Integer/String/Text/DateTime: tipos e colunas SQL
from sqlalchemy import Column, DateTime, Integer, String, Text, func

# Base: mesma base declarativa usada pelas demais tabelas
from ai_english_tutor.models.message import Base


# Classe StudentWord — vira a tabela `student_words` no PostgreSQL
# Herda de Base → automaticamente registrada no metadata do SQLAlchemy
class StudentWord(Base):
    """Uma palavra/frase no perfil: vocabulário estudado ou erro do aluno."""

    # Nome explícito da tabela no banco de dados
    __tablename__ = "student_words"

    # Chave primária autoincrementada (SEQUENCE do Postgres)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Dono da palavra — FK lógico para students.id (UUID)
    # index=True → acelera o filtro por aluno nos endpoints
    student_id = Column(String(36), nullable=False, index=True)

    # A palavra/frase em si (ex.: "goed" ou "daily routine")
    # String(200) cobre tanto termos curtos quanto fragmentos de frase
    word = Column(String(200), nullable=False)

    # Tipo: "vocabulary" (estudado) ou "mistake" (erro do aluno)
    # String(20) = cabe os dois valores
    kind = Column(String(20), nullable=False)

    # Detalhe opcional: para mistake → "correct — explanation";
    # para vocabulary → definição ou exemplo de uso (em PT)
    detail = Column(Text, nullable=True)

    # Momento do registro — server_default = NOW() do banco
    created_at = Column(
        DateTime(timezone=True),           # TIMESTAMP WITH TIME ZONE
        server_default=func.now(),         # preenchido automaticamente no INSERT
        nullable=False,
    )

    # Representação em texto para debug/log
    # Ex.: <StudentWord #3 student=a1b2 kind=mistake word='goed'>
    def __repr__(self) -> str:
        return (
            f"<StudentWord #{self.id} student={self.student_id} "
            f"kind={self.kind} word={self.word!r}>"
        )
