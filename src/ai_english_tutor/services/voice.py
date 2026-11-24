# ==============================================================================
# services/voice.py — módulo de Voz (Etapa 8)
# Responsabilidade única: STT (áudio -> texto) e TTS (texto -> áudio) via Groq.
# Dois limites importantes do Orpheus TTS: máximo de 200 caracteres por
# request e saída somente em WAV — por isso o texto é fatiado em pedaços
# pequenos, cada um vira um WAV, e os WAVs são remontados num só arquivo.
# ==============================================================================

# re: quebra o texto em frases para caber no limite de 200 chars
import re

# struct: lê/escreve os cabeçalhos binários do formato WAV (RIFF)
import struct

# Mesmas classes de erro do SDK usadas pelo Tutor (auth, rate limit, timeout...)
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

# Cliente OpenAI-compatible apontando para a Groq (mesmo SDK do Tutor)
from openai import OpenAI

# Configurações (.env) — STT_MODEL, TTS_MODEL, TTS_VOICE e URL/chave LLM
from ai_english_tutor.core.config import settings

# Erro de domínio: mensagem em PT + status HTTP (reutiliza o handler global)
from ai_english_tutor.services.tutor import TutorError


# Vozes válidas do modelo Orpheus English (documentadas na Groq)
TTS_VOICES = frozenset({"autumn", "diana", "hannah", "austin", "daniel", "troy"})

# Limite real do Orpheus é 200 chars/request — deixamos 190 de folga
# (margem p/ eventuais direction tags e evita estourar no limite exato)
_TTS_CHUNK_LIMIT = 190

# Tamanho máximo de arquivo aceito pela API de transcrição da Groq (25 MB)
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


# Classe VoiceService — expõe transcribe() e synthesize()
class VoiceService:
    """Converte áudio em texto (Whisper) e texto em áudio (Orpheus)."""

    # Construtor: um cliente LLM único (reusa URL/chave do .env)
    # Timeouts maiores que o chat: áudio pode demorar mais para processar
    def __init__(self) -> None:
        self._client = OpenAI(
            base_url=settings.LLM_BASE_URL,  # endpoint Groq (OpenAI-compatible)
            api_key=settings.LLM_API_KEY,    # chave do .env
            timeout=60.0,                     # STT/TTS aceitam mais lentidão
            max_retries=1,                    # 1 retry basta p/ mídia
        )

    # ------------------------------------------------------------------ STT
    # Método público: recebe bytes de áudio e devolve o texto transcrito
    def transcribe(self, filename: str, data: bytes) -> str:
        """Transcreve um arquivo de áudio (wav/mp3/m4a...) em texto."""

        # Validações baratas antes de gastar chamada à API
        if not data:
            raise TutorError("Arquivo de áudio vazio.", status_code=400)
        if len(data) > _MAX_AUDIO_BYTES:
            raise TutorError(
                "Áudio muito grande. O limite é 25 MB.", status_code=400
            )

        # Chama a API de transcrições (Whisper na Groq)
        try:
            # O SDK aceita tupla (nome, bytes) como "file" — não precisa
            # gravar o upload em disco temporário
            response = self._client.audio.transcriptions.create(
                model=settings.STT_MODEL,        # whisper-large-v3-turbo
                file=(filename or "audio.wav", data),
            )
        # Qualquer falha do SDK vira TutorError com o status HTTP correto
        except Exception as exc:
            self._translate(exc)                 # sempre levanta exceção

        # .text = texto transcrito (formato json padrão do Whisper)
        return (response.text or "").strip()

    # ------------------------------------------------------------------ TTS
    # Método público: recebe texto e devolve bytes WAV prontos p/ tocar
    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Sintetiza fala a partir de texto; fatia o texto se passar de 190 chars."""

        # Escolhe a voz: parâmetro > config > valida contra a lista oficial
        chosen = (voice or settings.TTS_VOICE).lower()
        if chosen not in TTS_VOICES:
            allowed = ", ".join(sorted(TTS_VOICES))
            raise TutorError(
                f"Voz inválida. Opções: {allowed}.", status_code=400
            )

        # Texto só em branco não tem o que falar
        if not text.strip():
            raise TutorError("Texto vazio para síntese de voz.", status_code=400)

        # Fatia o texto em pedaços de no máximo 190 caracteres
        pieces = _split_text(text)

        # Gera um WAV por pedaço (limite do Orpheus: 200 chars/request)
        blobs: list[bytes] = []
        for piece in pieces:
            blobs.append(self._speech(piece, chosen))

        # Um pedaço só → reescreve o header: a Groq envia os tamanhos do
        # RIFF/data como 0xFFFFFFFF (convenção de streaming) e regravamos
        # com o valor real — WAV final sempre válido em qualquer player
        if len(blobs) == 1:
            fmt, data = _split_wav(blobs[0])
            return _make_wav(fmt, data)

        # Vários pedaços → remonta num único WAV válido
        try:
            return _concat_wavs(blobs)
        except ValueError as exc:
            raise TutorError(
                "Não consegui montar o áudio final.", status_code=502
            ) from exc

    # Método interno: UMA chamada ao endpoint /audio/speech da Groq
    def _speech(self, piece: str, voice: str) -> bytes:
        """Pede um trecho de texto ao Orpheus e devolve os bytes WAV."""

        try:
            # response_format="wav" é o ÚNICO formato suportado pelo Orpheus
            response = self._client.audio.speech.create(
                model=settings.TTS_MODEL,   # canopylabs/orpheus-v1-english
                voice=voice,                 # autumn/diana/hannah/austin/...
                input=piece,                 # pedaço (<= 190 chars)
                response_format="wav",       # saída PCM em RIFF/WAVE
            )
        except Exception as exc:
            self._translate(exc)             # sempre levanta exceção

        # .content = bytes binários do arquivo WAV
        return response.content

    # Método interno: traduz exceções do SDK em TutorError com status certo
    @staticmethod
    def _translate(exc: Exception) -> None:
        """Mapeia falhas do SDK OpenAI para as mensagens/status do projeto."""

        # Chave inválida/revogada → 401 (mesma mensagem do Tutor)
        if isinstance(exc, AuthenticationError):
            raise TutorError(
                "Chave de API do LLM inválida. Verifique o arquivo .env.",
                status_code=401,
            ) from exc

        # Cota estourada → 429
        if isinstance(exc, RateLimitError):
            raise TutorError(
                "Limite de requisições do LLM atingido. Tente novamente em instantes.",
                status_code=429,
            ) from exc

        # Rede/timeout → 504
        if isinstance(exc, (APITimeoutError, APIConnectionError)):
            raise TutorError(
                "Não consegui falar com o modelo de IA. Verifique sua conexão.",
                status_code=504,
            ) from exc

        # A API respondeu com erro — 400 = problema no arquivo/texto enviado
        if isinstance(exc, APIStatusError) and exc.status_code == 400:
            # Caso especial: modelo de voz com termos pendentes de aceite
            # no console da Groq (Orpheus é preview e exige aceite único)
            body = getattr(exc, "body", None)
            code = body.get("code") if isinstance(body, dict) else None
            if code == "model_terms_required":
                raise TutorError(
                    "Aceite os termos do modelo de voz no console da Groq "
                    "(console.groq.com/playground) e tente novamente.",
                    status_code=400,
                ) from exc
            raise TutorError(
                "Não consegui processar esse áudio ou texto. Verifique o formato.",
                status_code=400,
            ) from exc

        # Qualquer outro status inesperado → 502 genérico
        if isinstance(exc, APIStatusError):
            raise TutorError(
                "O provedor de IA retornou um erro inesperado. Tente novamente.",
                status_code=502,
            ) from exc

        # Exceção não mapeada → 502 com contexto preservado
        raise TutorError(
            "Falha inesperada ao processar áudio.", status_code=502
        ) from exc


# ---------------------------------------------------------------------- helpers
# Função pura: quebra o texto em pedaços que respeitam o limite do Orpheus
def _split_text(text: str, limit: int = _TTS_CHUNK_LIMIT) -> list[str]:
    """Divide texto em blocos <= limit, preferindo fronteiras de frase."""

    # Normaliza espaços/quebras de linha duplicadas num espaço só
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return [normalized]

    # Primeiro separa em frases (. ! ? ;) — quebra natural de fala
    sentences = re.split(r"(?<=[.!?;:])\s+", normalized)

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        # Frase maior que o limite (sem pontuação útil) → corta nas palavras
        while len(sentence) > limit:
            # Última palavra antes do limite (evita cortar no meio da palavra)
            cut = sentence.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit             # palavra gigante: corte forçado
            # Se já havia texto acumulado, fecha o pedaço atual antes
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()

        if not sentence:
            continue                    # sobrou só espaço/pontuação

        # Acumula a frase no pedaço atual respeitando o limite
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= limit:
            current += " " + sentence
        else:
            chunks.append(current)       # não cabe: fecha e recomeça
            current = sentence

    # Fecha o último pedaço aberto
    if current:
        chunks.append(current)

    # Remove eventuais pedaços vazios gerados por normalização
    return [chunk for chunk in chunks if chunk]


# Função pura: extrai os campos "fmt " e "data" de um arquivo WAV
def _split_wav(blob: bytes) -> tuple[bytes, bytes]:
    """Parse mínimo de RIFF/WAVE: devolve (chunk fmt, payload data)."""

    # Cabeçalho mínimo: "RIFF" + tamanho + "WAVE"
    if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("não é um arquivo WAV válido")

    pos = 12                       # pula o cabeçalho RIFF/WAVE
    fmt: bytes | None = None
    data = b""

    # Percorre os subchunks (cada um: 4 bytes id + 4 bytes tamanho + corpo)
    while pos + 8 <= len(blob):
        chunk_id = blob[pos : pos + 4]
        (size,) = struct.unpack("<I", blob[pos + 4 : pos + 8])
        body = blob[pos + 8 : pos + 8 + size]

        if chunk_id == b"fmt ":
            fmt = body              # parâmetros: canais, taxa, bits...
        elif chunk_id == b"data":
            data = body             # amostras PCM brutas

        # Chunks são alinhados a 2 bytes (tamanho ímpar tem 1 byte de padding)
        pos += 8 + size + (size % 2)

    if fmt is None:
        raise ValueError("WAV sem chunk fmt")

    return fmt, data


# Função pura: monta um WAV completo a partir de fmt + amostras
def _make_wav(fmt: bytes, data: bytes) -> bytes:
    """Reescreve cabeçalho RIFF/WAVE com tamanhos corretos."""

    # Tamanho do RIFF = "WAVE"(4) + bloco fmt + bloco data (com headers)
    riff_size = 4 + (8 + len(fmt)) + (8 + len(data))

    out = bytearray()
    out += b"RIFF"
    out += struct.pack("<I", riff_size)
    out += b"WAVE"
    out += b"fmt " + struct.pack("<I", len(fmt)) + fmt
    out += b"data" + struct.pack("<I", len(data)) + data
    return bytes(out)


# Função pura: concatena vários WAVs (mesma taxa/canais) num só arquivo
def _concat_wavs(blobs: list[bytes]) -> bytes:
    """Junta pedaços WAV sequenciais; dados PCM são só concatenados.

    Aceita também WAVs com tamanhos de streaming (0xFFFFFFFF) como a
    Groq envia: o fatiamento usa o fim do arquivo como limite do chunk
    `data` (que sempre vem por último), e a remontagem grava tamanhos reais.
    """

    if not blobs:
        raise ValueError("lista de áudios vazia")

    # Usa o primeiro WAV como referência de formato (fmt) e acumula os dados
    fmt, first_data = _split_wav(blobs[0])
    payload = bytearray(first_data)

    for blob in blobs[1:]:
        next_fmt, next_data = _split_wav(blob)
        # Se o formato difere, a concatenação saria corrompida → erro
        if next_fmt != fmt:
            raise ValueError("WAVs com formatos diferentes")
        payload += next_data

    # Reescreve um único cabeçalho com o tamanho total do payload
    return _make_wav(fmt, bytes(payload))


# Instância singleton — cliente STT/TTS compartilhado por toda a aplicação
voice_service = VoiceService()
