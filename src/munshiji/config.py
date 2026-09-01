"""pydantic-settings loader for config/default.yaml. Phase 1."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


class AppConfig(BaseModel):
    name: str
    language: Literal["auto", "en", "hi", "gu"]
    first_run_wizard: bool


class AudioConfig(BaseModel):
    input_device: str
    sample_rate: int
    ring_buffer_s: float


class VadConfig(BaseModel):
    model: str
    silence_ms: int
    min_speech_ms: int


class WakeConfig(BaseModel):
    engine: str
    phrase: str
    threshold: float
    debounce_ms: int
    hotkey: str
    # Not in config/default.yaml's original keys — see docs/ROADMAP.md Phase 1
    # note: no "hey munshiji" openWakeWord model exists yet (training one is
    # a separate effort), so this names the actual model file/identifier the
    # detector loads. Defaults to a stock pretrained model as a placeholder.
    # (Named detector_model_id rather than model_id/model_name to avoid
    # pydantic v2's reserved "model_" field-name namespace.)
    detector_model_id: str = "hey_jarvis"


class AsrConfig(BaseModel):
    engine: str
    model: str
    compute_type: str
    backend: str
    device: str
    initial_prompt: str


class GrammarConfig(BaseModel):
    enabled: bool
    dirs: list[str]


class EmbeddingsConfig(BaseModel):
    enabled: bool
    model: str
    threshold: float
    examples: str


class RouterConfig(BaseModel):
    grammar: GrammarConfig
    embeddings: EmbeddingsConfig
    teach_mode: bool


class LlmConfig(BaseModel):
    enabled: bool
    provider: str
    model: str
    keep_alive: int
    history_turns: int
    max_tools_in_context: int
    max_iterations: int
    temperature: float


class CloudConfig(BaseModel):
    enabled: bool
    escalate: Literal["never", "ask", "auto"]


class TtsConfig(BaseModel):
    engine: str
    voice: str
    stream: bool
    indic_engine: str


class OverlayConfig(BaseModel):
    enabled: bool
    position: Literal["bottom_center", "bottom_left", "bottom_right"]
    width_px: int
    height_px: int
    margin_px: int
    opacity: float
    transcript_display_s: float


class UiConfig(BaseModel):
    overlay: OverlayConfig


class NetworkConfig(BaseModel):
    mode: Literal["local_only", "hybrid", "full"]
    inbound: Literal["none", "tailscale"]
    allowlist: list[str]
    timeout_s: int
    retries: int


class SecurityConfig(BaseModel):
    confirm_risk_tiers: list[str]
    blocked_tools: list[str]
    speaker_verification: bool
    undo_depth: int


class DocumentsConfig(BaseModel):
    enabled: bool
    path: str
    embed_model: str
    watch_dirs: list[str]


class MemoryConfig(BaseModel):
    facts_db: str
    documents: DocumentsConfig


class LoggingConfig(BaseModel):
    level: str
    audit: str
    rotate_mb: int


class MunshijiConfig(BaseSettings):
    """Root config, loaded from config/default.yaml. Env vars prefixed
    MUNSHIJI_ (e.g. MUNSHIJI_LLM__ENABLED=false) override individual keys —
    useful for CI and local overrides without editing the committed YAML.
    """

    model_config = SettingsConfigDict(env_prefix="MUNSHIJI_", env_nested_delimiter="__")

    app: AppConfig
    audio: AudioConfig
    vad: VadConfig
    wake: WakeConfig
    asr: AsrConfig
    router: RouterConfig
    llm: LlmConfig
    cloud: CloudConfig
    tts: TtsConfig
    ui: UiConfig
    network: NetworkConfig
    security: SecurityConfig
    memory: MemoryConfig
    logging: LoggingConfig


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> MunshijiConfig:
    """Load and validate config/default.yaml (or an override path)."""
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return MunshijiConfig.model_validate(raw)
