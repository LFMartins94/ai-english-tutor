# ==============================================================================
# schemas/planner.py — modelos de dados das requisições/respostas
# do plano de aula (POST /plan e GET /plan/{session_id}).
# Pydantic valida a estrutura do JSON: campo faltante ou tipo errado
# gera erro 400 automático antes de chegar na lógica de negócio.
# ==============================================================================

# BaseModel é a base de todos os modelos de dados do pydantic
from pydantic import BaseModel, Field


# Schema de ENTRADA — corpo esperado no POST /plan
class PlanRequest(BaseModel):
    """Payload para gerar um plano de aula para uma sessão."""

    # UUID da sessão — obrigatório (o plano lê nível + histórico dela)
    session_id: str = Field(
        ...,                          # ... = valor obrigatório, sem default
        min_length=1,                 # string vazia é rejeitada
        max_length=36,                # UUID canônico tem 36 caracteres
        description="ID da sessão para a qual o plano será gerado",
    )

    # UUID do aluno (opcional — vincula o plano ao perfil)
    # Com aluno, tópicos cobertos e plano vigente valem entre sessões
    student_id: str | None = Field(
        default=None,
        max_length=36,
        description="ID do aluno (POST /students); vincula o plano ao perfil",
    )


# Schema de SAÍDA — um tópico do plano (vocabulário/gramática/conversação)
class TopicOut(BaseModel):
    """Um tópico de aula: tipo, título curto e o que ensinar."""

    # Tipo do tópico: vocabulary | grammar | conversation
    kind: str = Field(
        ...,
        description="Tipo: vocabulary, grammar ou conversation",
    )

    # Título curto do tópico (ex.: "Daily routine")
    title: str = Field(..., description="Nome curto do tópico")

    # O que ensinar/praticar, em português (orientação para o tutor)
    detail: str = Field(..., description="O que ensinar neste tópico (PT)")


# Schema de SAÍDA — plano completo (POST /plan e GET /plan/{session_id})
class PlanResponse(BaseModel):
    """Plano de aula vigente de uma sessão."""

    # UUID da sessão do plano
    session_id: str = Field(..., description="ID da sessão do plano")

    # Nível do aluno quando o plano foi gerado (vem do Evaluator)
    level: str = Field(
        ...,
        description="Nível considerado no plano (beginner|basic|intermediate|advanced)",
    )

    # Proporção PT/EN vigente na época do plano (ex.: "70/30")
    pt_en_ratio: str = Field(
        ...,
        description="Proporção PT/EN do nível do plano",
    )

    # Objetivo da aula em uma frase — injetado no system prompt do chat
    focus: str = Field(..., description="Objetivo da aula em uma frase")

    # Os 3 tópicos na ordem didática: vocabulary → grammar → conversation
    topics: list[TopicOut] = Field(
        ...,
        min_length=1,
        description="Tópicos do plano na ordem de ensino",
    )

    # Justificativa breve em português
    rationale: str = Field(..., description="Por que este plano (PT)")
