# ==============================================================================
# schemas/evaluation.py — modelos de dados das requisições/respostas
# da avaliação de nível (POST /evaluate e GET /level/{session_id}).
# Pydantic valida a estrutura do JSON: campo faltante ou tipo errado
# gera erro 400 automático antes de chegar na lógica de negócio.
# ==============================================================================

# BaseModel é a base de todos os modelos de dados do pydantic
from pydantic import BaseModel, Field


# Schema de ENTRADA — corpo esperado no POST /evaluate
class EvaluateRequest(BaseModel):
    """Payload para avaliar o nível do aluno de uma sessão."""

    # UUID da sessão a avaliar — obrigatório (não há sessão implícita)
    # (a avaliação precisa do histórico já gravado no banco da sessão)
    session_id: str = Field(
        ...,                          # ... = valor obrigatório, sem default
        min_length=1,                 # string vazia é rejeitada
        max_length=36,                # UUID canônico tem 36 caracteres
        description="ID da sessão cujo histórico será avaliado",
    )

    # UUID do aluno (opcional — vincula a avaliação ao perfil)
    # Com aluno, o nível passa a valer em TODAS as sessões dele
    student_id: str | None = Field(
        default=None,
        max_length=36,
        description="ID do aluno (POST /students); vincula a avaliação ao perfil",
    )


# Schema de SAÍDA — corpo devolvido pelo POST /evaluate
class EvaluateResponse(BaseModel):
    """Resultado da avaliação de nível de uma sessão."""

    # UUID da sessão avaliada
    session_id: str = Field(..., description="ID da sessão avaliada")

    # Nível resultante: beginner | basic | intermediate | advanced
    level: str = Field(
        ...,
        description="Nível decidido pelo Evaluator (beginner|basic|intermediate|advanced)",
    )

    # Pontuação 0-100 (a faixa define o nível: 0-24, 25-49, 50-74, 75-100)
    score: int = Field(
        ge=0,
        le=100,
        description="Pontuação de competência (0-100)",
    )

    # Justificativa breve em português
    rationale: str = Field(..., description="Por que este nível foi decidido (PT)")

    # Proporção PT/EN que passa a valer para a sessão (ex.: "70/30")
    pt_en_ratio: str = Field(
        ...,
        description="Proporção PT/EN resultante (ex.: 70/30, 0/100)",
    )


# Schema de SAÍDA — corpo devolvido pelo GET /level/{session_id}
class LevelResponse(BaseModel):
    """Nível atual de uma sessão (sem executar nova avaliação)."""

    # UUID da sessão consultada
    session_id: str = Field(..., description="ID da sessão consultada")

    # Nível vigente: última avaliação, ou beginner se nunca avaliada
    level: str = Field(
        ...,
        description="Nível atual (default beginner antes da 1ª avaliação)",
    )

    # Proporção PT/EN vigente (ex.: "70/30")
    pt_en_ratio: str = Field(
        ...,
        description="Proporção PT/EN atual da sessão",
    )

    # true = a sessão já passou por pelo menos uma avaliação formal
    # false = nível é o default (beginner) porque ninguém avaliou ainda
    evaluated: bool = Field(
        ...,
        description="Se a sessão já foi avaliada pelo Evaluator",
    )
