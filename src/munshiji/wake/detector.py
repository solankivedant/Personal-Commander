"""openWakeWord detector, ~1-2% CPU continuous. Phase 1."""

from __future__ import annotations

import time

import numpy as np
import structlog
from openwakeword.model import Model
from openwakeword.utils import download_models

logger = structlog.get_logger(__name__)


class WakeWordDetector:
    """Wraps openWakeWord. `model_id` loads config.wake.model_id — see
    config/default.yaml's comment: there is no trained "hey munshiji" model
    yet, so this defaults to a stock pretrained phrase (hey_jarvis) as a
    stand-in until one is trained. Push-to-talk (wake/fsm.py) is the reliable
    entry point in the meantime.
    """

    def __init__(self, model_id: str, threshold: float, debounce_ms: int) -> None:
        self.model_id = model_id
        self.threshold = threshold
        self.debounce_ms = debounce_ms
        self._last_fire_at: float | None = None
        # download_models() is a no-op for files it already finds on disk, so
        # this is safe to call unconditionally on every boot rather than
        # reacting to Model()'s (inconsistent — sometimes ValueError,
        # sometimes an onnxruntime-internal NoSuchFile) failure modes.
        logger.info("wake_model_ensure_downloaded", model_id=model_id)
        download_models(model_names=[model_id])
        self._model = Model(wakeword_models=[model_id], inference_framework="onnx")

    def push_frame(self, frame: np.ndarray) -> bool:
        """Feed one audio frame (int16 mono); returns True if the wake word
        just fired (respecting the debounce window)."""
        predictions = self._model.predict(frame)
        score = predictions.get(self.model_id, 0.0)
        if score < self.threshold:
            return False

        now = time.monotonic()
        if self._last_fire_at is not None:
            elapsed_ms = (now - self._last_fire_at) * 1000
            if elapsed_ms < self.debounce_ms:
                return False
        self._last_fire_at = now
        logger.debug("wake_fire", model_id=self.model_id, score=score)
        return True

    def reset(self) -> None:
        self._model.reset()
