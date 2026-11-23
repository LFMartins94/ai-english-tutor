# ==============================================================================
# schemas/chat.py — modelos de dados das requisições/respostas do chat
# Pydantic valida a estrutura do JSON: campo faltante ou com tipo errado
# gera erro 422 automático antes de chegar na lógica de negócio.
# ==============================================================================

# BaseModel é a base de todos os modelos de dados do pydantic
from pydantic import BaseModel, Field


# Schema de ENTRADA — corpo esperado no POST /chat
# O FastAPI valida o JSON da request contra esta classe automaticamente
class ChatRequest(BaseModel):
    """Payload de uma mensagem enviada pelo aluno."""

    # Texto digitado/falado pelo aluno — obrigatório (sem default)
    message: str = Field(
        ...,                          # ... = valor obrigatório, sem default
        min_length=1,                 # string vazia é rejeitada
        max_length=4000,              # limite de segurança contra abusos
        description="Mensagem do aluno em PT ou EN",  # aparece no /docs
    )

    # UUID da sessão de conversa — agrupa as mensagens no PostgreSQL
    # Opcional: se ausente, o servidor gera um novo e devolve na resposta
    # (o frontend reenvia este id nos próximos turnos para continuar a conversa)
    session_id: str | None = Field(
        default=None,                 # default None = sessão nova a cada vez
        max_length=36,                # UUID canônico tem 36 caracteres
        description="ID da sessão; omitir para começar uma conversa nova",
    )

    # Histórico legado enviado pelo frontend — usado APENAS como fallback
    # quando ainda não há mensagens no banco para a sessão (compatibilidade)
    history: list[dict[str, str]] | None = Field(
        default=None,                 # default None = campo opcional
        description="Turnos anteriores (fallback; o banco é a fonte oficial)",
    )

    # UUID do aluno (perfil de memória de longo prazo — Etapa 7)
    # Opcional: se enviado, o turno é vinculado ao aluno e o tutor
    # recupera nível/foco/erros recorrentes do perfil entre sessões
    student_id: str | None = Field(
        default=None,                 # default None = sessão anônima
        max_length=36,                # UUID canônico tem 36 caracteres
        description="ID do aluno (POST /students); omitir para anônimo",
    )


# Schema de SAÍDA — corpo devolvido pelo POST /chat
# Garante que o cliente sempre recebe o mesmo formato, independente do LLM
class ChatResponse(BaseModel):
    """Resposta gerada pelo tutor."""

    # Texto da resposta do professor — sempre string (nunca None)
    reply: str = Field(
        ...,                          # obrigatório: a resposta não pode faltar
        description="Resposta do AI English Tutor",
    )

    # Modelo usado na geração — útil para logs e depuração no frontend
    model: str = Field(
        ...,                          # obrigatório: sempre informar qual modelo respondeu
        description="Identificador do LLM que gerou a resposta",
    )

    # ID da sessão — o cliente DEVE guardá-lo e reenviar no próximo turno
    # Mesmo que o cliente não tenha pedido, o servidor sempre devolve um
    session_id: str = Field(
        ...,
        description="ID da sessão para continuar a conversa no próximo POST /chat",
    )

    # Correções detectadas na mensagem do aluno deste turno
    # Lista vazia = aluno não errou nada (ou o Corrector não rodou)
    corrections: list["CorrectionOut"] = Field(
        default_factory=list,         # default = lista vazia
        description="Erros de inglês encontrados no turno atual",
    )


# Schema de SAÍDA — uma correção estruturada do módulo Corrector
class CorrectionOut(BaseModel):
    """Um erro detectado: frase errada → versão correta → explicação."""

    # Trecho incorreto escrito pelo aluno (verbatim)
    wrong: str = Field(..., description="Frase incorreta como o aluno escreveu")

    # Versão corrigida sugerida pelo tutor
    correct: str = Field(..., description="Versão corrigida da frase")

    # Explicação breve em português
    explanation: str = Field(..., description="Explicação do erro em PT")


# Schema de SAÍDA — uma linha do histórico (espelha a tabela messages)
class MessageOut(BaseModel):
    """Mensagem histórica devolvida pelo GET /history."""

    # Papel na conversa: "user" (aluno) ou "assistant" (tutor)
    role: str = Field(..., description="Quem falou: user ou assistant")

    # Texto da mensagem
    content: str = Field(..., description="Conteúdo da mensagem")

    # Data/hora do registro (ISO 8601 com fuso horário)
    created_at: str = Field(..., description="Momento da mensagem (ISO 8601)")


# Schema de SAÍDA — resposta completa do endpoint de histórico
class HistoryResponse(BaseModel):
    """Conversa recuperada de uma sessão."""

    # UUID da sessão consultado
    session_id: str = Field(..., description="ID da sessão consultada")

    # Lista cronológica de mensagens (mais antiga primeiro)
    messages: list[MessageOut] = Field(
        default_factory=list,         # default vazio se não houver mensagens
        description="Mensagens da sessão em ordem cronológica",
    )


# Schema de SAÍDA — um erro recorrente agrupado do GET /errors
class ErrorOut(BaseModel):
    """Frase errada com contagem de frequência na sessão."""

    # Frase incorreta agrupada
    wrong: str = Field(..., description="Frase errada (agrupada)")

    # Versão corrigida correspondente
    correct: str = Field(..., description="Versão corrigida")

    # Explicação da última ocorrência
    explanation: str = Field(..., description="Explicação em PT")

    # Quantas vezes o mesmo erro apareceu na sessão
    count: int = Field(..., ge=1, description="Frequência do erro (>= 1)")


# Schema de SAÍDA — relatório de erros recorrentes de uma sessão
class ErrorsResponse(BaseModel):
    """Erros do aluno ordenados dos mais frequentes para os menos."""

    # UUID da sessão consultado
    session_id: str = Field(..., description="ID da sessão consultada")

    # Lista de erros agrupados (mais frequentes primeiro)
    errors: list[ErrorOut] = Field(
        default_factory=list,
        description="Erros recorrentes ordenados por frequência",
    )
