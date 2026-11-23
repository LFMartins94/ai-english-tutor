# ==============================================================================
# services/history.py — persistência do histórico de conversas
# Responsabilidade única: salvar e recuperar mensagens do PostgreSQL.
# O endpoint orquestra: LLM gera → history.save() grava → response volta.
# ==============================================================================

# Session: tipo da sessão SQLAlchemy injetada pelo FastAPI via get_db()
from sqlalchemy.orm import Session

# Modelo ORM da tabela messages
from ai_english_tutor.models.message import Message


# Funções puras de CRUD — sem estado próprio, recebem a session por parâmetro
def save_message(
    db: Session,           # sessão ativa do request (injetada pelo FastAPI)
    session_id: str,       # UUID da conversa (agrupa as mensagens)
    role: str,             # "user" ou "assistant"
    content: str,          # texto da mensagem
    student_id: str | None = None,  # perfil do aluno (None = anônimo)
) -> Message:
    """Grava uma mensagem no banco e devolve a linha criada (com id)."""

    # Cria o objeto Message em memória — AINDA não tocou no banco
    # (SQLAlchemy rastreia a instância como "pendente de insert")
    message = Message(
        session_id=session_id,   # agrupador da conversa
        student_id=student_id,   # dono (perfil) quando vinculado
        role=role,               # quem falou
        content=content,         # o que foi dito
    )

    # Adiciona à sessão: marca para inserção no próximo flush/commit
    db.add(message)

    # Persiste imediatamente: INSERT + COMMIT numa única transação
    # Sem commit, os dados morreriam junto com a sessão do request
    db.commit()

    # Refresh busca o id/created_at gerados pelo banco de volta para o objeto
    # (o INSERT só popula esses campos depois de executado)
    db.refresh(message)

    # Devolve a linha completa — o endpoint pode querer o id/ timestamp
    return message


def get_history(
    db: Session,           # sessão ativa do request
    session_id: str,       # UUID da conversa a recuperar
    limit: int = 100,      # máximo de mensagens retornadas (proteção)
) -> list[Message]:
    """Retorna as mensagens de uma sessão em ordem cronológica."""

    # Query SQLAlchemy: SELECT * FROM messages WHERE session_id = :sid
    # filter_by é a forma declarativa (mais legível que filter(Message.session_id == ...))
    query = (
        db.query(Message)                          # SELECT ... FROM messages
        .filter_by(session_id=session_id)          # WHERE session_id = ?
        .order_by(Message.created_at.asc())        # ORDER BY data ASC (mais antiga 1º)
        .limit(limit)                              # LIMIT :limit (últimas N)
    )

    # .all() executa a query e devolve lista de objetos Message
    return query.all()
