# ==============================================================================
# ai_english_tutor/__init__.py — raiz do pacote da aplicação
# Marca o diretório como pacote Python e expõe o entrypoint principal.
# ==============================================================================

# Importa a função main() definida em main.py (será o entrypoint da API)
from ai_english_tutor.main import main

# Reexporta main() para que `ai_english_tutor:main` funcione no pyproject.toml
# Isso permite rodar o projeto com: uv run ai-english-tutor
__all__ = ["main"]
