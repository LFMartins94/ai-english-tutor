# ==============================================================================
# models/__init__.py — subpacote de modelos ORM (mapeamento tabela ↔ classe)
# Cada arquivo aqui define uma tabela do PostgreSQL como uma classe Python.
# ==============================================================================

# Reexporta o modelo Message para import direto: `from ai_english_tutor.models import Message`
from ai_english_tutor.models.message import Message

# Reexporta Correction (erros do aluno) para import direto pelo service/endpoint
from ai_english_tutor.models.correction import Correction

# Reexporta Evaluation (avaliações de nível) para o Evaluator e endpoints
from ai_english_tutor.models.evaluation import Evaluation

# Reexporta Plan (planos de aula) para o Planner e endpoints
from ai_english_tutor.models.plan import Plan

# Lista pública do módulo — define o que `from ... import *` expõe
__all__ = ["Message", "Correction", "Evaluation", "Plan"]
