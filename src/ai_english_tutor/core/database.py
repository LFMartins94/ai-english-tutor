# ==============================================================================
# core/database.py — infraestrutura de acesso ao PostgreSQL
# Cria a engine (pool de conexões) e a Session factory do SQLAlchemy.
# Separado do config para manter responsabilidade única: aqui é só "conectar".
# ==============================================================================

# create_engine: monta a engine que gerencia o pool de conexões com o banco
# sessionmaker: fábrica de sessões (cada request usa uma sessão curta)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Configurações centrais — DATABASE_URL vem do .env
from ai_english_tutor.core.config import settings

# Engine síncrona: usa o driver psycopg (v3) para falar com o PostgreSQL
# A URL já vem formatada no .env: postgresql+psycopg://user:senha@host/db
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # testa a conexão antes de cada uso do pool
                         # (evita erro "server closed the connection" após idle)
    pool_size=5,          # conexões mantidas abertas no pool
    max_overflow=10,      # conexões extras sob demanda (pico de tráfego)
)

# sessionmaker configurado com autocommit DESLIGADO (padrão SQLAlchemy 2.x)
# Cada sessão faz commit explícito — garante que só dados válidos persistam
SessionLocal = sessionmaker(
    bind=engine,          # aponta a fábrica para a engine criada acima
    autoflush=False,      # não empurra mudanças ao banco sem commit() explícito
    expire_on_commit=False,  # mantém atributos acessíveis após o commit
)


# Dependência do FastAPI: gera uma sessão por request e fecha ao final
# yield = estilo "context manager" — devolve a sessão, espera o endpoint
# terminar, e então executa o fechamento (garbage collection da conexão)
def get_db() -> Session:
    """Fornece uma Session do SQLAlchemy para um único request HTTP."""

    # Cria a sessão que será injetada no endpoint (parâmetro `db: Session`)
    db = SessionLocal()

    # try/finally garante que a conexão volte ao pool mesmo se o endpoint
    # lançar exceção — sem isso, a conexão vazaria (connection leak)
    try:
        yield db          # devolve a sessão para o FastAPI usar
    finally:
        db.close()        # devolve a conexão ao pool (não fecha o banco)
