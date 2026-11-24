# ==============================================================================
# schemas/voice.py — payloads das rotas de voz (Etapa 8)
# /transcribe: upload de áudio -> texto | /speak: texto -> bytes de áudio
# ==============================================================================

# BaseModel/Field: validação declarativa com mensagens de erro em PT
from pydantic import BaseModel, Field


# Resposta da transcrição (Whisper devolve só o texto; modelo p/ referência)
class TranscribeResponse(BaseModel):
    """Texto transcrito a partir do áudio enviado."""

    # Texto final limpo (pode ser vazio se o áudio não tiver fala)
    text: str = Field(..., description="Transcrição do áudio")

    # Modelo STT usado (whisper-large-v3-turbo) — útil p/ debug no cliente
    model: str = Field(..., description="Modelo de transcrição utilizado")


# Requisição da síntese de voz (texto -> WAV)
class SpeakRequest(BaseModel):
    """Texto que deve ser falado pelo tutor (TTS)."""

    # 1..4000: vazio não fala; 4000 limita o custo do TTS por request
    # (o service ainda fatia em blocos de 190 chars p/ o limite do Orpheus)
    text: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Texto para sintetizar (1 a 4000 caracteres)",
    )

    # Voz opcional das 6 vozes inglesas do Orpheus; None = voz do .env
    # pattern = validação em cima: voz fora da lista vira 400 no handler
    voice: str | None = Field(
        default=None,
        pattern="^(autumn|diana|hannah|austin|daniel|troy)$",
        description="Voz do Orpheus (autumn|diana|hannah|austin|daniel|troy)",
    )
