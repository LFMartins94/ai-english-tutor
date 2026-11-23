# ==============================================================================
# services/planner.py — módulo Planner (seleção de conteúdos e exercícios)
# Responsabilidade única: montar o próximo plano de aula (vocabulário,
# gramática, conversação) para o nível ATUAL do Evaluator, sem repetir
# tópicos já cobertos. Módulo LÓGICO da mesma aplicação.
# ==============================================================================

# json: parsing da saída estruturada (JSON do plano)
import json

# Cliente LLM (mesmo SDK/endpoint do Tutor — Groq OpenAI-compatible)
from openai import OpenAI

# Prompt + construtor de mensagens específicos do Planner
from ai_english_tutor.agents.prompts import build_planner_messages

# Configurações (.env) — reutiliza URL/chave/modelo do Tutor
from ai_english_tutor.core.config import settings

# Sessão SQLAlchemy — persistência dos planos no PostgreSQL
from sqlalchemy.orm import Session

# or_: combina filtros quando há aluno + sessão (último dos dois)
from sqlalchemy import or_

# Modelo ORM da tabela plans (gravação/leitura do plano vigente)
from ai_english_tutor.models.plan import Plan

# TutorError — erros do LLM viram resposta HTTP amigável (handler global)
from ai_english_tutor.services.tutor import TutorError


# Tipo de domínio: um tópico já "limpo" do plano
# (dataclass leve = só agrupa campos, sem validação pesada do pydantic)
from dataclasses import dataclass


# Estrutura imutável de um tópico de aula
@dataclass
class TopicItem:
    """Um tópico do plano: tipo, título e o que ensinar."""

    # vocabulary | grammar | conversation (validado no parse)
    kind: str

    # Título curto (ex.: "Daily routine")
    title: str

    # Orientação em português do que ensinar
    detail: str


# Estrutura imutável do resultado de uma geração de plano
@dataclass
class PlanResult:
    """Plano de aula: foco, 3 tópicos e justificativa."""

    # Objetivo da aula em uma frase (vai para o system prompt do chat)
    focus: str

    # Tópicos na ordem didática: vocabulary → grammar → conversation
    topics: list[TopicItem]

    # Justificativa breve em português
    rationale: str


# Classe PlannerService — expõe generate() + helpers de persistência
class PlannerService:
    """Monta planos de aula progressivos para a sessão do aluno."""

    # Construtor: cliente próprio (planejamento pode ser mais demorado)
    def __init__(self) -> None:
        # Mesma base URL/chave do Tutor — só muda o prompt e a tarefa
        self._client = OpenAI(
            base_url=settings.LLM_BASE_URL,  # endpoint Groq
            api_key=settings.LLM_API_KEY,    # chave do .env
            timeout=45.0,                     # raciocínio longo: mais folga
            max_retries=1,                    # 1 retry basta p/ planejamento
        )

    # Método público: gera o próximo plano dado nível/histórico/cobertos
    def generate(
        self,
        level: str,                                # nível do Evaluator
        history: list[dict[str, str]],             # conversa da sessão
        covered_topics: list[str],                 # tópicos já planejados
    ) -> PlanResult:
        """Retorna o plano estruturado (levanta TutorError em falha do LLM)."""

        # Monta o payload [system, user-contexto] — ver agents/prompts.py
        messages = build_planner_messages(level, history, covered_topics)

        # Tenta a chamada ao LLM — falha vira TutorError com status certo
        try:
            response = self._client.chat.completions.create(
                model=settings.LLM_MODEL,     # 120B: planejar exige qualidade
                messages=messages,             # nível + histórico + cobertos
                temperature=0.4,               # variedade entre aulas iguais
                # reasoning_effort=medium: planejamento pedagógico se beneficia
                # de raciocínio, sem o custo do effort=high do Evaluator
                reasoning_effort="medium",
                # 4096 = folga p/ reasoning extenso + JSON com 3 tópicos
                # (gpt-oss consome centenas de tokens "pensando" antes)
                max_tokens=4096,
            )

        # Qualquer falha (auth/rate/timeout/status) → erro amigável p/ a API
        except Exception as exc:
            raise TutorError(
                "Não consegui montar o plano agora. Tente novamente.",
                status_code=502,
            ) from exc

        # Texto bruto — pode vir com ```json ... ``` em volta
        raw = response.choices[0].message.content or ""

        # Parse defensivo: extrai e valida o JSON do plano
        return self._parse(raw)

    # Método interno: transforma o texto do LLM em PlanResult
    @staticmethod
    def _parse(raw: str) -> PlanResult:
        """Extrai e valida o JSON do plano; falha vira TutorError."""

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
            raise TutorError(                 # sem JSON = resposta inválida
                "O planejador devolveu uma resposta ilegível. Tente novamente.",
                status_code=502,
            )

        # Fatia só o trecho que parece JSON e tenta parsear
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise TutorError(                 # JSON malformado = ilegível
                "O planejador devolveu uma resposta ilegível. Tente novamente.",
                status_code=502,
            ) from exc

        # Pega a lista de tópicos; se não for lista → erro
        raw_topics = data.get("topics")
        if not isinstance(raw_topics, list):
            raise TutorError(
                "O planejador não devolveu tópicos válidos. Tente novamente.",
                status_code=502,
            )

        # Converte dicts em TopicItem, mantendo só os 3 kinds válidos
        # (tolera tópico extra do modelo: pegamos o 1º de cada tipo)
        valid_kinds = ("vocabulary", "grammar", "conversation")
        by_kind: dict[str, TopicItem] = {}
        for item in raw_topics:
            if not isinstance(item, dict):
                continue                      # pula lixo que o modelo inventou
            kind = str(item.get("kind", "")).strip().lower()
            title = item.get("title")
            detail = item.get("detail")
            # Só aceita se for um dos 3 kinds e title/detail forem válidos
            if kind not in valid_kinds or kind in by_kind:
                continue                      # kind inválido ou repetido → pula
            if not isinstance(title, str) or not title.strip():
                continue                      # título faltando/vazio → pula
            if not isinstance(detail, str) or not detail.strip():
                continue                      # detail faltando/vazio → pula
            by_kind[kind] = TopicItem(
                kind=kind,                    # vocabulary | grammar | conversation
                title=title.strip(),          # título curto
                detail=detail.strip(),        # orientação em PT
            )

        # Precisa ter os 3 kinds — plano incompleto é erro, não meio plano
        if any(k not in by_kind for k in valid_kinds):
            raise TutorError(
                "O planejador não devolveu os 3 tópicos (vocabulário, "
                "gramática, conversação). Tente novamente.",
                status_code=502,
            )

        # Ordena na ordem didática fixa: vocabulary → grammar → conversation
        topics = [by_kind[k] for k in valid_kinds]

        # Foco: string não vazia; se faltar, usa marcador neutro
        focus = data.get("focus")
        if not isinstance(focus, str) or not focus.strip():
            focus = "Praticar os tópicos do plano com o tutor."

        # Justificativa: string não vazia; se faltar, usa marcador neutro
        rationale = data.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            rationale = "Sem justificativa informada pelo planejador."

        # Tudo válido → resultado de domínio pronto para persistir
        return PlanResult(focus=focus.strip(), topics=topics, rationale=rationale)

    # ------------------------------------------------------------------
    # Persistência — linhas da tabela `plans` no PostgreSQL
    # ------------------------------------------------------------------

    @staticmethod
    def get_latest(
        db: Session,
        session_id: str | None = None,
        student_id: str | None = None,
    ) -> Plan | None:
        """Retorna o plano mais recente da sessão e/ou do aluno."""

        # Com aluno, vale o MAIS RECENTE entre os planos do perfil
        # (qualquer sessão) e os da sessão atual — plano vigente entre
        # conversas novas do mesmo aluno
        query = db.query(Plan)
        if student_id and session_id:
            query = query.filter(
                or_(
                    Plan.student_id == student_id,         # perfil do aluno
                    Plan.session_id == session_id,         # sessão atual
                )
            )
        elif student_id:
            query = query.filter(Plan.student_id == student_id)
        else:
            query = query.filter(Plan.session_id == session_id)

        # ORDER BY created_at DESC + LIMIT 1 = plano "vigente"
        # created_at é server_default=NOW(); empates raros resolvidos por id
        return (
            query.order_by(Plan.created_at.desc(), Plan.id.desc())
            .limit(1)                         # só o mais recente
            .first()
        )

    @staticmethod
    def get_covered_topics(
        db: Session,
        session_id: str | None = None,
        student_id: str | None = None,
    ) -> list[str]:
        """Títulos dos tópicos já planejados na sessão/aluno (histórico)."""

        # Busca todos os planos relevantes, do mais antigo ao mais recente
        # (com aluno, inclui planos de sessões anteriores — progressão real)
        query = db.query(Plan)
        if student_id and session_id:
            query = query.filter(
                or_(Plan.student_id == student_id, Plan.session_id == session_id)
            )
        elif student_id:
            query = query.filter(Plan.student_id == student_id)
        else:
            query = query.filter(Plan.session_id == session_id)

        rows = query.order_by(Plan.created_at.asc(), Plan.id.asc()).all()

        # Achata a lista JSON de cada plano em uma lista de títulos
        # (o Planner recebe isto para NÃO repetir nenhum tópico)
        titles: list[str] = []
        for row in rows:
            for topic in row.topics or []:     # row.topics já vem como list
                title = topic.get("title")     # pega o título do tópico
                if isinstance(title, str) and title.strip():
                    titles.append(title.strip())
        return titles

    @staticmethod
    def save(
        db: Session,
        session_id: str,
        level: str,
        result: PlanResult,
        student_id: str | None = None,
    ) -> Plan:
        """Grava um novo plano (passa a ser o vigente da sessão/aluno)."""

        # Converte TopicItem[] → list[dict] para a coluna JSON do banco
        topics_payload = [
            {"kind": t.kind, "title": t.title, "detail": t.detail}
            for t in result.topics
        ]

        # Monta a linha ORM — o commit é responsabilidade do endpoint
        # (mesmo padrão do /chat e /evaluate: endpoint commita uma vez)
        row = Plan(
            session_id=session_id,              # sessão do plano
            student_id=student_id,              # perfil (None = anônimo)
            level=level,                        # nível vigente na geração
            focus=result.focus,                 # objetivo da aula
            topics=topics_payload,              # 3 tópicos em JSON
            rationale=result.rationale,         # justificativa em PT
        )
        db.add(row)                            # INSERT na transação atual
        return row


# Instância singleton — compartilhada por toda a aplicação
planner_service = PlannerService()
