# ==============================================================================
# models/student.py — modelo ORM da tabela `students`
# Cada linha = UM aluno com perfil persistente entre sessões.
# É a base da memória de longo prazo (Etapa 7): nível, objetivos e
# idioma nativo sobrevivem a novas conversas.
# ==============================================================================

# Column/Integer/String/Text/DateTime: tipos e colunas SQL
from sqlalchemy import Column, DateTime, String, Text, func

# Base: mesma base declarativa usada pelas demais tabelas
from ai_english_tutor.models.message import Base


# Classe Student — vira a tabela `students` no PostgreSQL
# Herda de Base → automaticamente registrada no metadata do SQLAlchemy
class Student(Base):
    """Perfil do aluno: identidade, objetivos e idioma nativo."""

    # Nome explícito da tabela no banco de dados
    __tablename__ = "students"

    # UUID do aluno — PK manual (gerado pelo endpoint com uuid4)
    # String(36) = formato canônico do UUID (mesmo das sessões)
    id = Column(String(36), primary_key=True)

    # Nome exibido (opcional — o aluno pode ser anônimo)
    name = Column(String(100), nullable=True)

    # Objetivos de aprendizado em português (ex.: "trabalhar no exterior")
    # Text = sem limite de tamanho (objetivos podem ser detalhados)
    goals = Column(Text, nullable=True)

    # Idioma nativo do aluno — default "pt-BR" (público do projeto)
    native_language = Column(String(20), nullable=False, server_default="pt-BR")

    # Momento do cadastro — server_default = NOW() do banco
    created_at = Column(
        DateTime(timezone=True),           # TIMESTAMP WITH TIME ZONE
        server_default=func.now(),         # preenchido automaticamente no INSERT
        nullable=False,
    )

    # Representação em texto para debug/log
    # Ex.: <Student a1b2c3... name='Luiz' goals='trabalhar...'>
    def __repr__(self) -> str:
        return f"<Student {self.id} name={self.name!r} goals={(self.goals or '')[:20]!r}>"
