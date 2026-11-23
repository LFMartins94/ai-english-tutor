# ==============================================================================
# schemas/student.py — modelos de dados das requisições/respostas
# do perfil do aluno (memória de longo prazo — Etapa 7).
# Pydantic valida a estrutura do JSON: campo faltante ou tipo errado
# gera erro 400 automático antes de chegar na lógica de negócio.
# ==============================================================================

# BaseModel é a base de todos os modelos de dados do pydantic
from pydantic import BaseModel, Field


# Schema de ENTRADA — corpo esperado no POST /students
class StudentCreate(BaseModel):
    """Payload para cadastrar um novo aluno."""

    # Nome exibido (opcional — o aluno pode ser anônimo)
    name: str | None = Field(
        default=None,
        max_length=100,
        description="Nome do aluno (opcional)",
    )

    # Objetivos de aprendizado em português (opcional)
    goals: str | None = Field(
        default=None,
        max_length=2000,
        description="O que o aluno quer alcançar com o inglês (PT)",
    )

    # Idioma nativo — default "pt-BR" no servidor (público do projeto)
    native_language: str | None = Field(
        default=None,
        max_length=20,
        description="Idioma nativo do aluno (default pt-BR)",
    )


# Schema de SAÍDA — perfil devolvido por POST/GET /students
class StudentResponse(BaseModel):
    """Perfil persistente de um aluno."""

    # UUID do aluno — o cliente DEVE guardá-lo (reenviar nos turnos)
    student_id: str = Field(..., description="ID do aluno para continuar vinculado")

    # Nome exibido (None se anônimo)
    name: str | None = Field(default=None, description="Nome do aluno")

    # Objetivos de aprendizado (None se não informado)
    goals: str | None = Field(default=None, description="Objetivos em PT")

    # Idioma nativo (default "pt-BR")
    native_language: str = Field(
        ...,
        description="Idioma nativo do aluno (ex.: pt-BR)",
    )


# Schema de ENTRADA — corpo esperado no POST /students/{id}/words
class WordCreate(BaseModel):
    """Payload para registrar vocabulário ou erro no perfil do aluno."""

    # A palavra/frase (ex.: "daily routine" ou "I am agree")
    word: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Palavra ou frase a registrar",
    )

    # Tipo: vocabulary (estudado) ou mistake (erro do aluno)
    kind: str = Field(
        ...,
        pattern="^(vocabulary|mistake)$",
        description="vocabulary ou mistake",
    )

    # Detalhe opcional: definição/uso (vocabulary) ou correção (mistake)
    detail: str | None = Field(
        default=None,
        max_length=1000,
        description="Detalhe opcional: uso/correção em PT",
    )


# Schema de SAÍDA — uma palavra/frase do perfil
class WordOut(BaseModel):
    """Uma entrada de vocabulário ou erro do aluno."""

    # A palavra/frase registrada
    word: str = Field(..., description="Palavra ou frase")

    # vocabulary | mistake
    kind: str = Field(..., description="Tipo da entrada")

    # Detalhe opcional (definição ou correção)
    detail: str | None = Field(default=None, description="Detalhe em PT")

    # Momento do registro (ISO 8601)
    created_at: str = Field(..., description="Momento do registro (ISO 8601)")


# Schema de SAÍDA — lista de palavras do perfil
class WordsResponse(BaseModel):
    """Vocabulário e erros registrados no perfil do aluno."""

    # UUID do aluno consultado
    student_id: str = Field(..., description="ID do aluno consultado")

    # Lista de entradas (filtro de kind aplicado no servidor)
    words: list[WordOut] = Field(
        default_factory=list,
        description="Palavras do perfil (vocabulário e/ou erros)",
    )


# Schema de SAÍDA — uma avaliação no histórico de evolução
class EvaluationHistoryOut(BaseModel):
    """Uma avaliação do aluno (ponto da curva de evolução)."""

    # Nível na época da avaliação
    level: str = Field(..., description="Nível avaliado")

    # Pontuação 0-100
    score: int = Field(..., ge=0, le=100, description="Pontuação (0-100)")

    # Momento da avaliação (ISO 8601)
    created_at: str = Field(..., description="Momento da avaliação (ISO 8601)")


# Schema de SAÍDA — métricas de evolução do aluno
class MetricsResponse(BaseModel):
    """Histórico de evolução e desempenho do aluno."""

    # UUID do aluno consultado
    student_id: str = Field(..., description="ID do aluno consultado")

    # Nível vigente (última avaliação; default beginner)
    current_level: str = Field(..., description="Nível atual do aluno")

    # Quantas sessões o aluno já teve (mensagens distintas)
    sessions_count: int = Field(..., ge=0, description="Sessões com mensagens")

    # Total de mensagens trocadas (aluno + tutor)
    messages_count: int = Field(..., ge=0, description="Total de mensagens")

    # Total de correções recebidas
    corrections_count: int = Field(..., ge=0, description="Correções acumuladas")

    # Contagem de vocabulário registrado
    vocabulary_count: int = Field(..., ge=0, description="Palavras de vocabulário")

    # Contagem de erros registrados
    mistake_count: int = Field(..., ge=0, description="Erros registrados")

    # Curva de evolução: avaliações em ordem cronológica
    evaluations: list[EvaluationHistoryOut] = Field(
        default_factory=list,
        description="Avaliações em ordem (evolução do score)",
    )


# Schema de SAÍDA — contexto recuperado para novas sessões
class ContextResponse(BaseModel):
    """Memória do aluno pronta para injetar numa conversa nova."""

    # UUID do aluno
    student_id: str = Field(..., description="ID do aluno")

    # Perfil básico
    name: str | None = Field(default=None, description="Nome do aluno")
    goals: str | None = Field(default=None, description="Objetivos em PT")
    native_language: str = Field(..., description="Idioma nativo")

    # Estado de ensino atual (nível + proporção)
    current_level: str = Field(..., description="Nível vigente")
    pt_en_ratio: str = Field(..., description="Proporção PT/EN (ex.: 70/30)")

    # Foco do plano vigente (se houver plano para o aluno)
    lesson_focus: str | None = Field(
        default=None,
        description="Foco da aula do plano vigente",
    )

    # Erros mais frequentes (top 5) — o tutor evita/reforça esses pontos
    top_mistakes: list[WordOut] = Field(
        default_factory=list,
        description="Erros recorrentes do aluno",
    )

    # Últimos vocabulários registrados (até 10)
    learned_words: list[WordOut] = Field(
        default_factory=list,
        description="Vocabulário estudado recentemente",
    )
