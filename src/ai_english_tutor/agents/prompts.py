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


# ==============================================================================
# NÍVEIS — vocabulário compartilhado do ensino adaptativo
# O level é um dos 4 valores abaixo; a proporção PT/EN é fixa por nível
# e só muda quando o Evaluator grava uma nova avaliação no banco.
# ==============================================================================

# Nível padrão de uma sessão que ainda NÃO foi avaliada.
# (70% PT / 30% EN — seguro para qualquer aluno recém-chegado)
DEFAULT_LEVEL = "beginner"

# Proporção PT/EN de cada nível — usada em prompts e na resposta da API.
# Chaves: valores válidos de level (qualquer outro é rejeitado na avaliação)
LEVEL_RATIOS: dict[str, str] = {
    "beginner": "70/30",        # 70% português / 30% inglês
    "basic": "50/50",           # meio a meio
    "intermediate": "20/80",    # imersão pesada no inglês
    "advanced": "0/100",        # 100% inglês (0% português)
}


# Função auxiliar que monta a lista de mensagens para a API do LLM.
# A API OpenAI-compatible espera um histórico [{"role", "content"}, ...];
# esta função injeta a system message e normaliza o formato das mensagens.
def build_messages(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    level: str = DEFAULT_LEVEL,
    lesson_focus: str | None = None,
    memory_context: str | None = None,
) -> list[dict[str, str]]:
    """Monta o payload: system (nível, foco, memória) + histórico + mensagem."""

    # Lista final que será enviada ao modelo — começa com a persona do tutor
    messages: list[dict[str, str]] = []

    # A instrução de sistema ganha o nível ATUAL da sessão no final:
    # o modelo lê a política geral (TUTOR_SYSTEM_PROMPT) e sabe qual
    # proporção PT/EN aplicar AGORA (lida do banco via GET/avaliação)
    system_prompt = (
        TUTOR_SYSTEM_PROMPT
        + f"\nCURRENT LEVEL: {level} — apply its PT/EN ratio strictly.\n"
    )

    # Foco da aula (gerado pelo Planner, se houver plano para a sessão):
    # o tutor conduz a conversa na direção do tópico planejado
    if lesson_focus:
        system_prompt += f"CURRENT LESSON FOCUS: {lesson_focus}\n"

    # Memória de longo prazo (Etapa 7): objetivos do aluno e erros
    # recorrentes vindos do perfil — o tutor reforça pontos fracos
    if memory_context:
        system_prompt += f"STUDENT MEMORY:\n{memory_context}\n"

    # Adiciona a instrução de sistema (comportamento do professor + nível)
    messages.append({"role": "system", "content": system_prompt})

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


# ==============================================================================
# EVALUATOR — avaliação de nível do aluno (módulo lógico separado do Tutor)
# Chamada SEPARADA com o histórico da sessão: julga o nível atual e devolve
# JSON estruturado. Único caminho que pode alterar o nível do aluno.
# ==============================================================================

# Prompt do Evaluator — pede SAÍDA JSON estruturada para parse confiável.
# Regra de ouro do roadmap: julga por COMPETÊNCIA, nunca por tempo decorrido.
EVALUATOR_SYSTEM_PROMPT = """\
You are an English level evaluator for Brazilian students.

INPUT: a conversation history (student messages have role "user").
TASK: judge the STUDENT's English level using only evidence from the
student's own messages (ignore tutor messages when judging).

Criteria, by weight:
1. Grammar accuracy in the student's English
2. Vocabulary range and word choice
3. Sentence complexity and fluency
4. Comprehension of and response to English prompts

Levels and score bands (score MUST match the level's band):
- beginner:     0-24   — minimal English, PT fallback, basic fragments
- basic:        25-49  — simple tenses, common words, short sentences
- intermediate: 50-74  — varied tenses, fewer errors, longer constructions
- advanced:     75-100 — near-natural accuracy, idioms, complex structures

Rules:
- NEVER judge by conversation length or time — only by competence.
- If the student barely wrote in English, that is evidence of beginner.
- If history is empty, return: {"level":"beginner","score":0,...}

OUTPUT: strict JSON only, no markdown, no commentary:
{"level":"<beginner|basic|intermediate|advanced>","score":<0-100>,"rationale":"<brief PT explanation, max 30 words>"}
"""


# Monta as mensagens da chamada do Evaluator (system + histórico da sessão)
# O histórico chega como [{"role","content"}, ...] — o modelo vê a conversa
# inteira e julga apenas as falas do aluno (role "user")
def build_evaluator_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Payload para o LLM avaliar o nível: system + histórico da sessão."""

    # Instrução de sistema: define critérias, faixas e formato JSON
    messages: list[dict[str, str]] = [
        {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
    ]

    # Histórico completo como um único turno "user" com a conversa transcrita
    # (formato transcript evita que o modelo confunda papéis no JSON de saída)
    transcript_lines = [
        f"{turn['role']}: {turn['content']}"     # ex.: "user: I went to school"
        for turn in history                        # para cada turno da sessão
    ]
    transcript = "\n".join(transcript_lines)       # une em bloco multilinha

    messages.append({"role": "user", "content": transcript})

    # Lista pronta para a API do LLM
    return messages


# ==============================================================================
# PLANNER — planejador de aulas (módulo lógico separado do Tutor)
# Chamada SEPARADA com nível + histórico + tópicos já cobertos:
# monta o próximo plano de aula (vocabulário, gramática, conversação)
# respeitando o nível vindo do Evaluator e evitando repetição.
# ==============================================================================

# Prompt do Planner — pede SAÍDA JSON estruturada para parse confiável.
# Regras centrais: 1 vocabulário + 1 gramática + 1 conversa, na ordem
# didática, no nível correto e SEM repetir o que já foi coberto.
PLANNER_SYSTEM_PROMPT = """\
You are a lesson planner for a Brazilian student learning English.

INPUT: current level, recent conversation transcript, and titles of
topics already covered in previous plans.
TASK: design the NEXT lesson plan (one short tutoring session).

Levels and what fits each band:
- beginner:     greetings, self-introduction, numbers, colors, family,
                "to be" in present simple; very basic vocabulary
- basic:        daily routine, simple past, food/places vocabulary,
                short practical dialogues
- intermediate: opinions/feelings, present perfect, idioms/phrasal
                verbs, longer discussions about experiences
- advanced:     formal vs informal register, nuanced vocabulary,
                abstract topics, debates and professional situations

Rules:
- Return EXACTLY 3 topics in teaching order:
  1) vocabulary, 2) grammar, 3) conversation (one of each kind)
- NEVER repeat a topic already covered (list provided) — progress
  on what came before instead of restarting
- Match the level strictly: no advanced grammar for a beginner
- Each topic must fit a short chat-based tutoring session

OUTPUT: strict JSON only, no markdown, no commentary:
{"topics":[{"kind":"vocabulary","title":"<short name>","detail":"<what to teach, PT, max 20 words>"},{"kind":"grammar","title":"<short name>","detail":"<what to teach, PT, max 20 words>"},{"kind":"conversation","title":"<short name>","detail":"<what to practice, PT, max 20 words>"}],"focus":"<one sentence describing the lesson goal>","rationale":"<why this plan fits, PT, max 30 words>"}
"""


# Monta as mensagens da chamada do Planner (system + dados da sessão)
# Entra: nível atual (do Evaluator), histórico recente e tópicos cobertos
def build_planner_messages(
    level: str,
    history: list[dict[str, str]],
    covered_topics: list[str],
) -> list[dict[str, str]]:
    """Payload para o LLM montar o plano: system + contexto da sessão."""

    # Instrução de sistema: define níveis, regras e formato JSON de saída
    messages: list[dict[str, str]] = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
    ]

    # Contexto da sessão num único turno user (transcript + cobertos)
    # Formato key: value torna o payload fácil de ler para o modelo
    transcript_lines = [
        f"{turn['role']}: {turn['content']}"     # ex.: "user: I went to school"
        for turn in history                        # para cada turno da sessão
    ]
    transcript = "\n".join(transcript_lines) or "(no conversation yet)"

    # Tópicos já planejados antes — o Planner não pode repetir nenhum
    covered = ", ".join(covered_topics) if covered_topics else "(none yet)"

    user_payload = (
        f"CURRENT LEVEL: {level}\n"
        f"TOPICS ALREADY COVERED: {covered}\n"
        f"RECENT CONVERSATION:\n{transcript}"
    )

    messages.append({"role": "user", "content": user_payload})

    # Lista pronta para a API do LLM
    return messages
