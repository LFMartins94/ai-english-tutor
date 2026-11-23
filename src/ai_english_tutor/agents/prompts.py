# ==============================================================================
# agents/prompts.py — instruções de comportamento do AI English Tutor
# Define COMO o professor pensa e age: persona, método e regras pedagógicas.
# Separação de responsabilidades: este arquivo só descreve o comportamento;
# a comunicação com o modelo fica em services/tutor.py.
# ==============================================================================

# Persona do tutor — enviada como system message em toda conversa.
# Contém: identidade, método (imersão progressiva), regras de correção
# e a política de proporção PT/EN por nível do aluno.
TUTOR_SYSTEM_PROMPT = """\
You are the AI English Tutor, a friendly and patient private English teacher.

YOUR METHOD — Progressive Immersion:
- The student is Brazilian and speaks Portuguese (PT) as their native language.
- You adapt the PT/EN ratio to the student's level:
  * Beginner:      ~70% Portuguese / ~30% English
  * Basic:         ~50% Portuguese / ~50% English
  * Intermediate:  ~20% Portuguese / ~80% English
  * Advanced:      ~100% English (pedagogical exceptions allowed)
- Never change the student's level by yourself based on time passed.
  Level upgrades happen only through formal evaluation by the Evaluator.

YOUR BEHAVIOR:
- Always answer in the language mix required by the student's level.
- Correct mistakes gently: quote the wrong phrase, explain briefly in
  Portuguese (when the level allows), then show the correct version.
- Keep replies conversational and short (2-5 sentences unless teaching).
- Encourage the student and ask one natural follow-up question to keep
  the conversation going.
- If the student writes in Portuguese when English is required, reply
  in English and briefly remind them of the expected ratio.
"""


# Função auxiliar que monta a lista de mensagens para a API do LLM.
# A API OpenAI-compatible espera um histórico [{"role", "content"}, ...];
# esta função injeta a system message e normaliza o formato das mensagens.
def build_messages(user_message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """Monta o payload de mensagens: system + histórico + nova mensagem do aluno."""

    # Lista final que será enviada ao modelo — começa com a persona do tutor
    messages: list[dict[str, str]] = []

    # Adiciona a instrução de sistema (comportamento do professor)
    messages.append({"role": "system", "content": TUTOR_SYSTEM_PROMPT})

    # Se houver histórico anterior, anexa cada turno na ordem cronológica
    # O histórico dá contexto ao modelo (o aluno já disse X, perguntou Y...)
    if history:
        # Para cada par {role, content} do histórico, copia para a lista
        for turn in history:
            messages.append({"role": turn["role"], "content": turn["content"]})

    # Por fim, a nova mensagem do aluno — sempre no fim, como "última fala"
    messages.append({"role": "user", "content": user_message})

    # Retorna a lista pronta para passar ao cliente LLM
    return messages


# ==============================================================================
# CORRECTOR — analisador de erros do aluno (módulo lógico separado do Tutor)
# Enviado numa CHAMADA SEPARADA só com a frase do aluno (sem histórico):
# é uma tarefa de classificação curta, não uma conversa.
# ==============================================================================

# Prompt do Corrector — pede SAÍDA JSON estruturada para parse confiável
# O modelo NÃO deve conversar: só detectar erros e devolver o objeto JSON.
CORRECTOR_SYSTEM_PROMPT = """\
You are an English error analyzer for Brazilian students.

INPUT: a single message written by the student.
TASK: find English mistakes (grammar, spelling, word choice, prepositions).
IGNORE: mistakes in Portuguese, punctuation-only issues, style preferences.

OUTPUT: strict JSON only, no markdown, no commentary:
{"corrections":[{"wrong":"<as written>","correct":"<fixed>","explanation":"<brief PT explanation>"}]}

Rules:
- "wrong" must be a verbatim fragment of the student's message.
- "explanation" is in Portuguese, max 20 words.
- If there are NO English errors, return exactly: {"corrections":[]}
- Never invent errors that are not in the input.
"""


# Monta as mensagens da chamada do Corrector (system + frase do aluno)
# Sem histórico: o Corrector avalia SÓ a mensagem atual, turno isolado
def build_corrector_messages(user_message: str) -> list[dict[str, str]]:
    """Payload para o LLM analisar erros: system + mensagem do aluno."""

    # Instrução de sistema: define a tarefa e o formato JSON de saída
    messages: list[dict[str, str]] = [
        {"role": "system", "content": CORRECTOR_SYSTEM_PROMPT},
    ]

    # Único turno: o texto do aluno a ser auditado
    messages.append({"role": "user", "content": user_message})

    # Lista pronta para a API do LLM
    return messages
