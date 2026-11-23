# ==============================================================================
# services/corrector.py — módulo Corrector (análise de erros do aluno)
# Responsabilidade única: auditar a frase do aluno e devolver correções
# estruturadas. Módulo LÓGICO da mesma aplicação (não um agente separado).
# ==============================================================================

# json: parsing da saída estruturada que pedimos ao LLM
import json

# Cliente LLM (mesmo SDK/endpoint do Tutor — Groq OpenAI-compatible)
from openai import OpenAI

# Prompt + construtor de mensagens específicos do Corrector
from ai_english_tutor.agents.prompts import build_corrector_messages

# Configurações (.env) — reutiliza URL/chave/modelo já usados pelo Tutor
from ai_english_tutor.core.config import settings


# Tipo de domínio: uma correção já "limpa" para salvar/retornar
# (dataclass leve = só agrupa campos, sem validação pesada do pydantic)
from dataclasses import dataclass


# Estrutura imutável de uma correção detectada
@dataclass
class CorrectionItem:
    """Um erro do aluno: frase errada, versão correta e explicação."""

    # Trecho incorreto extraído verbatim da mensagem do aluno
    wrong: str

    # Versão corrigida sugerida pelo analisador
    correct: str

    # Explicação breve em português (por que era errado)
    explanation: str


# Classe CorrectorService — expõe analyze(): frase → lista de correções
class CorrectorService:
    """Audita mensagens do aluno e devolve erros em formato estruturado."""

    # Construtor: cliente próprio (pode ter timeout menor que o do Tutor)
    def __init__(self) -> None:
        # Mesma base URL/chave do Tutor — só muda o prompt e a tarefa
        self._client = OpenAI(
            base_url=settings.LLM_BASE_URL,  # endpoint Groq
            api_key=settings.LLM_API_KEY,    # chave do .env
            timeout=15.0,                     # tarefa curta: aborta mais cedo
            max_retries=1,                    # 1 retry basta p/ análise curta
        )

    # Método público: analisa UMA mensagem e devolve lista de correções
    def analyze(self, user_message: str) -> list[CorrectionItem]:
        """Retorna os erros de inglês encontrados (lista vazia se não houver)."""

        # Monta o payload [system, user] — ver agents/prompts.py
        messages = build_corrector_messages(user_message)

        # Tenta a chamada ao LLM; QUALQUER falha vira lista vazia
        # Filosofia degradação-graceful: o chat NÃO pode quebrar porque
        # o corrector falhou — reply do tutor já é a resposta principal
        try:
            response = self._client.chat.completions.create(
                model=settings.LLM_MODEL,   # mesmo modelo do Tutor
                messages=messages,           # task prompt + frase do aluno
                temperature=0.0,             # 0 = determinístico (análise fixa)
                # gpt-oss-120b é modelo de REASONING: gasta dezenas de tokens
                # "pensando" antes de gerar o JSON. 500 bastavam só pro
                # raciocínio e cortavam a resposta (finish_reason=length).
                # 2048 dá folga p/ reasoning + JSON completo de correções.
                max_tokens=2048,
            )

        # Qualquer exceção de rede/auth/rate-limit → sem correções (não quebra)
        except Exception:
            return []

        # Texto bruto da resposta — pode vir com ```json ... ``` em volta
        raw = response.choices[0].message.content or ""

        # Parse defensivo: extrai o objeto JSON mesmo com cercas de markdown
        return self._parse(raw)

    # Método interno: transforma o texto do LLM em CorrectionItem[]
    @staticmethod
    def _parse(raw: str) -> list[CorrectionItem]:
        """Extrai e valida o JSON das correções; devolve [] se inválido."""

        # Limpa cercas de código (```json ... ```) que modelos às vezes emitem
        text = raw.strip()
        if text.startswith("```"):            # remove abertura de fence
            text = text.split("```", 2)[1]    # pega o miolo entre ```s
        if text.startswith("json"):           # remove tag "json" residual
            text = text[4:].strip()

        # Localiza o objeto JSON { ... } mesmo com lixo antes/depois
        start = text.find("{")                # índice do primeiro {
        end = text.rfind("}")                 # índice do último }
        if start == -1 or end == -1 or end <= start:
            return []                         # sem JSON → sem correções

        # Fatia só o trecho que parece JSON e tenta parsear
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []                         # JSON malformado → ignora

        # Pega a lista sob a chave "corrections"; se não for lista → []
        items = data.get("corrections", [])
        if not isinstance(items, list):
            return []

        # Converte cada dict em CorrectionItem, descartando campos inválidos
        result: list[CorrectionItem] = []
        for item in items:
            # Só aceita se os 3 campos existirem e forem strings não vazias
            if not isinstance(item, dict):
                continue                      # pula lixo que o modelo inventou
            wrong = item.get("wrong")
            correct = item.get("correct")
            explanation = item.get("explanation")
            if not all(isinstance(v, str) and v for v in (wrong, correct, explanation)):
                continue                      # campo faltando/vazio → pula
            # Campos OK → monta o objeto de domínio
            result.append(
                CorrectionItem(
                    wrong=wrong,              # frase errada (verbatim)
                    correct=correct,          # versão corrigida
                    explanation=explanation,  # explicação em PT
                )
            )

        # Lista final validada (pode ser vazia = aluno errou nada)
        return result


# Instância singleton — cliente LLM reutilizado em todos os requests
corrector_service = CorrectorService()
