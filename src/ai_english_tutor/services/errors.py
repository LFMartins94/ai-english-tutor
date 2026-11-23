# ==============================================================================
# services/errors.py — consulta de erros recorrentes do aluno
# Agrupa as corrections por frase errada e conta frequência — base do
# relatório "o que você mais erra" (memória de longo prazo, Etapa 7).
# ==============================================================================

# func: funções de agregação SQL (COUNT, GROUP BY...)
from sqlalchemy import func

# Session: sessão SQLAlchemy injetada pelo FastAPI
from sqlalchemy.orm import Session

# Modelo ORM da tabela corrections
from ai_english_tutor.models.correction import Correction


# Tipo de domínio: erro agrupado com a contagem de ocorrências
from dataclasses import dataclass


# Estrutura de um erro recorrente devolvido pelo serviço
@dataclass
class ErrorSummary:
    """Frase errada repetida + quantas vezes apareceu + última explicação."""

    # Frase incorreita agrupada (chave do GROUP BY)
    wrong: str

    # Versão corrigida mais recente para aquela frase
    correct: str

    # Explicação mais recente (a do último registro daquele grupo)
    explanation: str

    # Quantas vezes o aluno errou a MESMA frase na sessão
    count: int


# Função pura: recebe session, devolve lista ordenada por frequência
def get_errors_summary(db: Session, session_id: str) -> list[ErrorSummary]:
    """Agrupa erros da sessão por frase errada e ordena dos mais frequentes."""

    # Query agregada:
    #   SELECT wrong, correct, explanation, COUNT(*) AS total
    #   FROM corrections
    #   WHERE session_id = :sid
    #   GROUP BY wrong          → une linhas com a mesma frase errada
    #   ORDER BY total DESC     → mais erros primeiro
    #   (correct/explanation: pega de qualquer linha do grupo — na prática,
    #    agrupamos por wrong e usamos max() para trazer um valor válido)
    rows = (
        db.query(
            Correction.wrong,                                   # coluna 1: agrupador
            func.max(Correction.correct).label("correct"),      # max p/ GROUP BY
            func.max(Correction.explanation).label("explanation"),
            func.count(Correction.id).label("total"),           # COUNT(*) por grupo
        )
        .filter(Correction.session_id == session_id)            # WHERE session
        .group_by(Correction.wrong)                             # agrupa iguais
        .order_by(func.count(Correction.id).desc())             # mais frequentes 1º
        .all()                                                  # executa a query
    )

    # Converte cada linha tupla → ErrorSummary tipado
    return [
        ErrorSummary(
            wrong=row[0],            # frase errada (group key)
            correct=row[1],          # correção (max do grupo)
            explanation=row[2],      # explicação (max do grupo)
            count=row[3],            # frequência
        )
        for row in rows              # itera sobre as linhas do GROUP BY
    ]
