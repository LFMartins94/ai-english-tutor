# ==============================================================================
# services/tutor.py — integração com o modelo de linguagem (LLM)
# Responsabilidade única: enviar mensagens ao modelo e devolver a resposta.
# Cliente OpenAI-compatible: apontando base_url para a Groq, o mesmo SDK
# serve outros provedores (OpenAI, DeepSeek, vLLM local...) sem mudar código.
# ==============================================================================

# Cliente síncrono da API compatível com OpenAI — usamos o da Groq
from openai import OpenAI

# Classes de erro do SDK: permitem tratar cada falha de forma específica
# (chave inválida, rate limit, timeout, erro interno do provedor...)
from openai import (
    APIConnectionError,     # falha de rede ao tentar falar com a API
    APIStatusError,         # a API respondeu com status de erro (4xx/5xx)
    APITimeoutError,        # a API demorou demais e a conexão estourou o timeout
    AuthenticationError,    # chave de API inválida ou revogada (HTTP 401)
    RateLimitError,         # cota de requisições excedida (HTTP 429)
)

# Instância de configuração (settings) vinda do core/config.py
from ai_english_tutor.core.config import settings

# Construtor de mensagens (system + histórico + user) do agents/prompts.py
from ai_english_tutor.agents.prompts import build_messages


# Exceção de domínio do projeto: erros do tutor viram HTTP 502 na API
# Herda de Exception para ser capturada como erro comum no FastAPI
class TutorError(Exception):
    """Erro de integração com o LLM, com mensagem amigável para o aluno."""

    # Mensagem final exibida ao usuário (em PT, para não quebrar a imersão)
    # Código HTTP sugerido: 401 auth, 429 rate limit, 504 timeout, 502 genérico
    def __init__(self, message: str, status_code: int = 502) -> None:
        # Chama o construtor de Exception com a mensagem (padrão Python)
        super().__init__(message)
        # Guarda o status HTTP que o endpoint deve devolver
        self.status_code = status_code


# Classe TutorService — expõe um único método: responder ao aluno
class TutorService:
    """Serviço de conversa: envia o prompt ao LLM e devolve a resposta em texto."""

    # Método construtor: cria o cliente LLM uma única vez por instância
    # Reaproveitar o cliente evita reconexões custosas a cada mensagem
    def __init__(self) -> None:
        # Instancia o cliente OpenAI apontando para a base URL do .env (Groq)
        # api_key vem da env var LLM_API_KEY — jamais hardcoded no código
        self._client = OpenAI(
            base_url=settings.LLM_BASE_URL,  # endpoint da Groq (OpenAI-compatible)
            api_key=settings.LLM_API_KEY,    # chave de autenticação do aluno
            timeout=30.0,                     # aborta a chamada após 30 segundos
            max_retries=2,                    # tenta de novo 2x antes de falhar
        )

    # Método público: gera a resposta do tutor para uma mensagem do aluno
    def reply(
        self,
        user_message: str,                     # texto escrito/falado pelo aluno
        history: list[dict[str, str]] | None = None,  # turnos anteriores da sessão
        level: str = "beginner",               # nível ATUAL lido do banco
        lesson_focus: str | None = None,       # foco do plano (se houver)
    ) -> str:
        """Constrói as mensagens, chama o modelo e devolve apenas o texto da resposta."""

        # Monta o payload [system+level+focus, *history, user] — ver prompts.py
        # O level define a proporção PT/EN; o focus orienta a aula do turno
        messages = build_messages(user_message, history, level, lesson_focus)

        # Tenta falar com o LLM; qualquer falha vira TutorError com status certo
        try:
            # Chamada síncrona ao modelo: temperature=0.7 equilibra
            # criatividade da conversa com consistência das correções
            response = self._client.chat.completions.create(
                model=settings.LLM_MODEL,  # modelo definido no .env (gpt-oss-120b)
                messages=messages,          # histórico completo formatado
                temperature=0.7,            # 0=robotico, 1=muito criativo; 0.7 = natural
            )

        # Chave errada/revogada → HTTP 401 na nossa API, mensagem clara em PT
        except AuthenticationError as exc:
            raise TutorError(
                "Chave de API do LLM inválida. Verifique o arquivo .env.",
                status_code=401,
            ) from exc  # `from exc` preserva o erro original no traceback

        # Cota estourada (muitas requisições) → HTTP 429, aluno pode tentar depois
        except RateLimitError as exc:
            raise TutorError(
                "Limite de requisições do LLM atingido. Tente novamente em instantes.",
                status_code=429,
            ) from exc

        # Rede fora do ar / timeout → HTTP 504, problema de conectividade
        except (APITimeoutError, APIConnectionError) as exc:
            raise TutorError(
                "Não consegui falar com o modelo de IA. Verifique sua conexão.",
                status_code=504,
            ) from exc

        # Qualquer outro status de erro (4xx/5xx inesperado) → HTTP 502 genérico
        except APIStatusError as exc:
            raise TutorError(
                "O provedor de IA retornou um erro inesperado. Tente novamente.",
                status_code=502,
            ) from exc

        # Extrai o texto da primeira (e única) choice da resposta da API
        # .choices[0] = primeira opção gerada; .message.content = texto final
        return response.choices[0].message.content or ""


# Instância singleton do serviço — compartilhada por toda a aplicação
# Criada no import: o cliente LLM é aberto uma vez e reutilizado
tutor_service = TutorService()
