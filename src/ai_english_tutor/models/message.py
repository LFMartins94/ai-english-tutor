# ==============================================================================
# models/message.py — modelo ORM da tabela `messages`
# Mapeia cada linha do histórico de conversa para um objeto Python.
# O SQLAlchemy gera o CREATE TABLE a partir destas definições.
# ==============================================================================

# Column: define cada coluna da tabela (tipo, constraints, default...)
# Integer/String/Text/DateTime: tipos de dados SQL equivalentes em Python
# DateTime: coluna de data/hora (timezone=True = guarda com fuso horário)
from sqlalchemy import Column, DateTime, Integer, String, Text, func

# DeclarativeBase: classe base que registra as subclasses como tabelas
# (padrão SQLAlchemy 2.x — substitui o antigo declarative_base())
from sqlalchemy.orm import DeclarativeBase


# Base vazia: todas as models herdam dela e são automaticamente mapeadas
# Criada uma única vez aqui para evitar círculos de import entre models
class Base(DeclarativeBase):
    """Base comum a todos os modelos ORM do projeto."""


# Classe Message — vira a tabela `messages` no PostgreSQL
# Cada atributo = uma coluna; cada instância = uma linha da tabela
class Message(Base):
    """Uma mensagem da conversa (do aluno ou do tutor) em uma sessão."""

    # Nome da tabela no banco — explícito para não depender do nome da classe
    __tablename__ = "messages"

    # Chave primária: identificador único de cada mensagem
    # autoincrement=True → o próprio Postgres gera o número (SEQUENCE)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identificador da sessão de conversa (UUID gerado no endpoint)
    # index=True → cria índice acelerado: GET /history filtra por ele
    # String(36) → espaço para UUID no formato canônico (36 caracteres)
    session_id = Column(String(36), nullable=False, index=True)

    # Quem falou: "user" (aluno) ou "assistant" (tutor)
    # String(20) + nullable=False → obrigatório, curto (cabe em 20 chars)
    role = Column(String(20), nullable=False)

    # Conteúdo textual da mensagem — Text = TEXT do Postgres (sem limite 255)
    content = Column(Text, nullable=False)

    # Data/hora do registro — func.now() = NOW() do banco (padrão do servidor)
    # onupdate=func.now() → atualiza automaticamente se a linha for editada
    created_at = Column(
        DateTime(timezone=True),           # TIMESTAMP WITH TIME ZONE
        server_default=func.now(),         # valor padrão: instante do INSERT
        nullable=False,                    # sempre preenchido
    )

    # Representação em texto ao imprimir o objeto (debug/log)
    # Ex.: <Message #1 session=abc123 role=user>
    def __repr__(self) -> str:
        return f"<Message #{self.id} session={self.session_id} role={self.role}>"
