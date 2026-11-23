# ==============================================================================
# services/students.py — módulo Memory (memória de longo prazo do aluno)
# Responsabilidade única: perfil persistente entre sessões — cadastro,
# vocabulário/erros, métricas de evolução e recuperação de contexto.
# Módulo LÓGICO da mesma aplicação (não um agente separado).
# ==============================================================================

# uuid4: gera o UUID do aluno no cadastro (PK manual)
from uuid import uuid4

# func: funções de agregação SQL (COUNT, COUNT DISTINCT)
from sqlalchemy import func

# or_: combina filtros (última avaliação do aluno OU da sessão atual)
from sqlalchemy import or_

# Sessão SQLAlchemy — persistência no PostgreSQL
from sqlalchemy.orm import Session

# Modelos ORM: perfil, palavras, mensagens, correções, avaliações e planos
from ai_english_tutor.models.correction import Correction
from ai_english_tutor.models.evaluation import Evaluation
from ai_english_tutor.models.message import Message
from ai_english_tutor.models.plan import Plan
from ai_english_tutor.models.student import Student
from ai_english_tutor.models.student_word import StudentWord

# Schema de entrada do cadastro (validação pydantic)
from ai_english_tutor.schemas.student import StudentCreate

# TutorError — erro de domínio com status HTTP (handler global converte)
from ai_english_tutor.services.tutor import TutorError


# Classe StudentsService — expõe CRUD do perfil + memória derivada
class StudentsService:
    """Serviço de memória de longo prazo: perfil, palavras, métricas, contexto."""

    # ------------------------------------------------------------------
    # Perfil (tabela students)
    # ------------------------------------------------------------------

    @staticmethod
    def create(db: Session, payload: StudentCreate) -> Student:
        """Cadastra um novo aluno e devolve a linha criada."""

        # UUID v4 gerado no servidor — o cliente recebe e reutiliza
        student = Student(
            id=str(uuid4()),                          # PK única do aluno
            name=payload.name,                        # pode ser None (anônimo)
            goals=payload.goals,                      # pode ser None
            native_language=payload.native_language or "pt-BR",  # default pt-BR
        )
        db.add(student)                               # INSERT na transação
        return student

    @staticmethod
    def get(db: Session, student_id: str) -> Student | None:
        """Retorna o aluno por ID (ou None se não existir)."""

        # get() é o atalho do SQLAlchemy p/ SELECT por chave primária
        return db.get(Student, student_id)

    @staticmethod
    def require(db: Session, student_id: str) -> Student:
        """Retorna o aluno ou levanta 404 (para endpoints com {student_id})."""

        student = StudentsService.get(db, student_id)
        if student is None:
            raise TutorError(                        # status 404 via handler
                "Aluno não encontrado. Cadastre com POST /students.",
                status_code=404,
            )
        return student

    # ------------------------------------------------------------------
    # Vocabulário e erros (tabela student_words)
    # ------------------------------------------------------------------

    @staticmethod
    def add_word(
        db: Session,
        student_id: str,
        word: str,
        kind: str,                                   # vocabulary | mistake
        detail: str | None = None,
    ) -> StudentWord:
        """Registra uma palavra/frase no perfil (dedupe por palavra+tipo)."""

        # Normaliza: sem espaços nas pontas, minúsculas p/ comparação
        normalized = word.strip()

        # Já existe a mesma palavra+tipo para este aluno? → atualiza detalhe
        # (evita duplicar "goed/mistake" a cada turno em que ele erra)
        existing = (
            db.query(StudentWord)
            .filter(
                StudentWord.student_id == student_id,
                StudentWord.word == normalized,
                StudentWord.kind == kind,
            )
            .first()
        )
        if existing is not None:
            # Só sobrescreve o detalhe se o novo for informativo
            if detail and detail.strip():
                existing.detail = detail.strip()
            return existing                           # reutiliza a linha

        # Linha nova no perfil do aluno
        row = StudentWord(
            student_id=student_id,                    # dono da palavra
            word=normalized,                          # palavra/frase
            kind=kind,                                # vocabulary | mistake
            detail=detail.strip() if detail else None,  # opcional
        )
        db.add(row)                                  # INSERT na transação
        return row

    @staticmethod
    def get_words(
        db: Session,
        student_id: str,
        kind: str | None = None,
    ) -> list[StudentWord]:
        """Lista as palavras do aluno, opcionalmente filtradas por tipo."""

        # SELECT ... WHERE student_id = ? [AND kind = ?] ORDER BY created_at
        query = (
            db.query(StudentWord)
            .filter(StudentWord.student_id == student_id)
            .order_by(StudentWord.created_at.desc(), StudentWord.id.desc())
        )
        if kind:
            query = query.filter(StudentWord.kind == kind)
        return query.all()

    @staticmethod
    def record_mistakes(
        db: Session,
        student_id: str,
        mistakes: list[tuple[str, str, str]],         # (wrong, correct, expl)
    ) -> None:
        """Grava erros do Corrector no perfil do aluno (dedupe por frase)."""

        for wrong, correct, explanation in mistakes:
            # Formata o detalhe: versão corrigida + explicação em PT
            detail = f"{correct} — {explanation}"
            # add_word deduplica: repetir o mesmo erro não cria linha nova
            StudentsService.add_word(
                db,
                student_id,
                word=wrong,                           # frase errada do aluno
                kind="mistake",                       # tipo: erro
                detail=detail,                        # correção + explicação
            )

    # ------------------------------------------------------------------
    # Métricas de evolução (agregações nas tabelas existentes)
    # ------------------------------------------------------------------

    @staticmethod
    def get_metrics(db: Session, student_id: str) -> dict:
        """Contadores + curva de avaliações do aluno (para /metrics)."""

        # Sessões distintas em que o aluno falou (COUNT DISTINCT session_id)
        sessions_count = (
            db.query(func.count(func.distinct(Message.session_id)))
            .filter(Message.student_id == student_id)
            .scalar()                                # devolve um int
            or 0
        )

        # Total de mensagens (aluno + tutor) vinculadas ao perfil
        messages_count = (
            db.query(func.count(Message.id))
            .filter(Message.student_id == student_id)
            .scalar()
            or 0
        )

        # Total de correções recebidas pelo aluno
        corrections_count = (
            db.query(func.count(Correction.id))
            .filter(Correction.student_id == student_id)
            .scalar()
            or 0
        )

        # Contagem de vocabulário e de erros no perfil (tabela student_words)
        vocabulary_count = (
            db.query(func.count(StudentWord.id))
            .filter(
                StudentWord.student_id == student_id,
                StudentWord.kind == "vocabulary",
            )
            .scalar()
            or 0
        )
        mistake_count = (
            db.query(func.count(StudentWord.id))
            .filter(
                StudentWord.student_id == student_id,
                StudentWord.kind == "mistake",
            )
            .scalar()
            or 0
        )

        # Curva de evolução: avaliações do aluno em ordem cronológica
        eval_rows = (
            db.query(Evaluation)
            .filter(Evaluation.student_id == student_id)
            .order_by(Evaluation.created_at.asc(), Evaluation.id.asc())
            .all()
        )
        evaluations = [
            {
                "level": row.level,                  # nível na época
                "score": row.score,                  # score 0-100
                "created_at": row.created_at.isoformat(),  # ISO 8601
            }
            for row in eval_rows
        ]

        # Nível vigente: última avaliação, ou default beginner
        current_level = evaluations[-1]["level"] if evaluations else "beginner"

        # Dicionário montado — o endpoint converte no schema pydantic
        return {
            "student_id": student_id,
            "current_level": current_level,
            "sessions_count": int(sessions_count),
            "messages_count": int(messages_count),
            "corrections_count": int(corrections_count),
            "vocabulary_count": int(vocabulary_count),
            "mistake_count": int(mistake_count),
            "evaluations": evaluations,
        }

    # ------------------------------------------------------------------
    # Recuperação de contexto em novas sessões
    # ------------------------------------------------------------------

    @staticmethod
    def get_context(db: Session, student_id: str) -> dict:
        """Memória pronta p/ injetar numa conversa nova (perfil + estado)."""

        # Perfil (nível vem das avaliações; foco vem do plano vigente)
        student = StudentsService.require(db, student_id)

        # Última avaliação do ALUNO (vale em qualquer sessão dele)
        latest_eval = (
            db.query(Evaluation)
            .filter(Evaluation.student_id == student_id)
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
            .limit(1)
            .first()
        )
        current_level = latest_eval.level if latest_eval else "beginner"

        # Último plano do ALUNO (foco da aula vigente entre sessões)
        latest_plan = (
            db.query(Plan)
            .filter(Plan.student_id == student_id)
            .order_by(Plan.created_at.desc(), Plan.id.desc())
            .limit(1)
            .first()
        )
        lesson_focus = latest_plan.focus if latest_plan else None

        # Top 5 erros MAIS FREQUENTES (GROUP BY word + COUNT)
        # O tutor usa isto para reforçar pontos fracos do aluno
        # IMPORTANTE: o ORDER BY só pode usar colunas do GROUP BY
        # (ordenar por id quebraria o GROUP BY do PostgreSQL)
        mistake_rows = (
            db.query(StudentWord.word, StudentWord.detail, func.count().label("n"))
            .filter(
                StudentWord.student_id == student_id,
                StudentWord.kind == "mistake",
            )
            .group_by(StudentWord.word, StudentWord.detail)
            .order_by(func.count().desc(), StudentWord.word.asc())
            .limit(5)
            .all()
        )
        top_mistakes = [
            {
                "word": row.word,                    # frase errada recorrente
                "kind": "mistake",                   # tipo fixo
                "detail": row.detail,                # correção + explicação
                "created_at": "",                    # sem data neste agregado
            }
            for row in mistake_rows
        ]

        # Últimos 10 vocabulários registrados (mais recentes primeiro)
        vocab_rows = (
            db.query(StudentWord)
            .filter(
                StudentWord.student_id == student_id,
                StudentWord.kind == "vocabulary",
            )
            .order_by(StudentWord.created_at.desc(), StudentWord.id.desc())
            .limit(10)
            .all()
        )
        learned_words = [
            {
                "word": row.word,                    # palavra estudada
                "kind": row.kind,                    # vocabulary
                "detail": row.detail,                # uso/definição em PT
                "created_at": row.created_at.isoformat(),
            }
            for row in vocab_rows
        ]

        # Dicionário montado — o endpoint converte no schema pydantic
        return {
            "student_id": student.id,
            "name": student.name,
            "goals": student.goals,
            "native_language": student.native_language,
            "current_level": current_level,
            "pt_en_ratio": "",                       # preenchido pelo endpoint
            "lesson_focus": lesson_focus,
            "top_mistakes": top_mistakes,
            "learned_words": learned_words,
        }

    @staticmethod
    def build_memory_context(db: Session, student_id: str) -> str | None:
        """Resumo em texto p/ injetar no system prompt do Tutor.

        Usado no POST /chat quando o aluno está vinculado: objetivos +
        erros recorrentes entram na memória da conversa atual.
        """

        student = StudentsService.get(db, student_id)
        if student is None:
            return None                               # aluno inválido → nada

        lines: list[str] = []

        # Objetivos de aprendizado (se informados no cadastro)
        if student.goals and student.goals.strip():
            lines.append(f"Student goals: {student.goals.strip()}")

        # Erros recorrentes: o tutor deve observar/reforçar esses pontos
        mistakes = StudentsService.get_context(db, student_id)["top_mistakes"]
        if mistakes:
            wrong_list = "; ".join(m["word"] for m in mistakes)
            lines.append(f"Recurring mistakes to watch: {wrong_list}")

        # None quando não há nada a injetar (prompt fica limpo)
        return "\n".join(lines) if lines else None


# Instância singleton — compartilhada por toda a aplicação
students_service = StudentsService()
