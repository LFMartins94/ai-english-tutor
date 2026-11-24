# ==============================================================================
# core/config.py — configuração central da aplicação
# Lê variáveis de ambiente (ou .env) e as expõe como objeto tipado.
# Padrão: pydantic-settings (validação + type hints + auto-load de .env).
# ==============================================================================

# Importa BaseSettings: como um BaseModel do pydantic, mas que também lê env vars
from pydantic_settings import BaseSettings, SettingsConfigDict

# AliasChoices permite aceitar MAIS DE UM nome de env var para o mesmo campo
# (ex.: LLM_API_KEY ou GROQ_API_KEY — o aluno pode usar qualquer um)
from pydantic import AliasChoices, Field


# Classe Settings — única fonte de verdade de configuração do projeto
# Herda de BaseSettings: cada atributo é lido de variáveis de ambiente
# (ou do arquivo .env apontado em model_config) com prioridade sobre o default.
class Settings(BaseSettings):
    """Configurações carregadas do ambiente/.env com validação automática."""

    # URL base da API do provedor LLM (Groq no caso, compatível com OpenAI)
    # Sobrescrevível pela env var LLM_BASE_URL — permite trocar de provedor
    # sem alterar código: basta mudar o valor no .env
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"

    # Chave de API usada para autenticar requisições ao provedor
    # Nunca terá valor default: obrigatória, senão o Settings() falha ao iniciar
    # validation_alias: aceita LLM_API_KEY (padrão) ou GROQ_API_KEY (atalho)
    LLM_API_KEY: str = Field(
        validation_alias=AliasChoices("LLM_API_KEY", "GROQ_API_KEY"),
    )

    # Identificador do modelo que receberá os prompts (gpt-oss-120b na Groq)
    LLM_MODEL: str = "openai/gpt-oss-120b"

    # Modelo do Corrector — tarefa curta de classificação (JSON de erros),
    # então usamos o 20B: 2x mais rápido e metade do preço que o 120B
    LLM_MODEL_CORRECTOR: str = "openai/gpt-oss-20b"

    # Modelo de STT (voz -> texto): whisper large v3 turbo na Groq
    STT_MODEL: str = "whisper-large-v3-turbo"

    # Modelo de TTS (texto -> voz): Orpheus English na Groq
    # Limite: 200 caracteres por request — por isso o service fatia o texto
    TTS_MODEL: str = "canopylabs/orpheus-v1-english"

    # Voz padrão do TTS (uma das 6 vozes inglesas do Orpheus)
    TTS_VOICE: str = "autumn"

    # URL de conexão com o PostgreSQL (dialect+driver://user:senha@host:porta/db)
    # O SQLAlchemy usa esta string para criar a engine de acesso ao banco
    DATABASE_URL: str = "postgresql+psycopg://tutor:tutor123@localhost:5432/ai_english_tutor"

    # Configuração do pydantic-settings apontando para o arquivo .env
    # env_file=".env" → carrega variáveis do arquivo; env_file_encoding → UTF-8
    # extra="ignore" → ignora chaves desconhecidas no .env em vez de quebrar
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instância única (singleton) criada no import do módulo
# Todos os arquivos que precisam de config importam `settings` daqui,
# garantindo que só exista um conjunto de configuração em memória
settings = Settings()
