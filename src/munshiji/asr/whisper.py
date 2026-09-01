"""faster-whisper `small`, int8, CPU transcription with cached per-session
language detection. Phase 1."""

from __future__ import annotations

import numpy as np
import structlog
from faster_whisper import WhisperModel

logger = structlog.get_logger(__name__)

# asr/openvino.py stays a Phase 6 stub (see its docstring) — the OpenVINO
# iGPU path measured ~850ms in the Phase 0 spike, short of the 600ms gate,
# with INT8 quantization identified as the untried next lever
# (docs/PHASE-0-RESULTS.md). Until that lands, config's `asr.backend:
# openvino` resolves to this CTranslate2 CPU backend with a logged warning
# rather than silently doing nothing.
SUPPORTED_BACKEND = "ctranslate2-cpu"


class WhisperAsr:
    """Wraps faster-whisper. Detects language once per session and caches it
    — re-detecting per utterance costs time and can flip-flop mid-session,
    per docs/ARCHITECTURE.md L2.
    """

    def __init__(
        self,
        model_size: str,
        compute_type: str,
        backend: str,
        initial_prompt: str,
    ) -> None:
        if backend != SUPPORTED_BACKEND:
            logger.warning(
                "asr_backend_fallback",
                requested=backend,
                using=SUPPORTED_BACKEND,
                reason="asr/openvino.py is still a Phase 6 stub",
            )
        self._model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        self._initial_prompt = initial_prompt
        self._session_language: str | None = None

    def reset_session(self) -> None:
        self._session_language = None

    def transcribe(self, pcm_int16: np.ndarray, sample_rate: int) -> str:
        if sample_rate != 16_000:
            raise ValueError(f"WhisperAsr requires 16kHz audio, got {sample_rate}Hz")
        audio = pcm_int16.astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(
            audio,
            language=self._session_language,
            initial_prompt=self._initial_prompt,
            vad_filter=False,  # endpointing already happened in audio/vad.py
        )
        segments = list(segments)
        if self._session_language is None:
            self._session_language = info.language
            logger.debug("asr_language_detected", language=info.language)
        return " ".join(s.text.strip() for s in segments).strip()
