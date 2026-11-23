# ==============================================================================
# models/__init__.py — subpacote de modelos ORM (mapeamento tabela ↔ classe)
# Cada arquivo aqui define uma tabela do PostgreSQL como uma classe Python.
# ==============================================================================

# Reexporta o modelo Message para import direto: `from ai_english_tutor.models import Message`
from ai_english_tutor.models.message import Message

# Reexporta Correction (erros do aluno) para import direto pelo service/endpoint
from ai_english_tutor.models.correction import Correction

# Lista pública do módulo — define o que `from ... import *` expõe
__all__ = ["Message", "Correction"]
