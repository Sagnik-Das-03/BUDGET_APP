import json
import logging
import re
import threading
from typing import Any, Optional

from app.llm.config import EAGER_TASKS, TASK_MODEL, model_path

logger = logging.getLogger("budget_tracker.llm")

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)

try:
    import litert_lm
    _IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - missing package, or Python < 3.10
    litert_lm = None
    _IMPORT_ERROR = exc


class LLMRouter:
    """Routes an AI task to whichever local model is configured for it
    (see app/llm/config.TASK_MODEL), loading each referenced model's Engine
    once and reusing it for every request. `warm_up()` loads every configured
    model eagerly (call at app startup) so the first real request isn't the
    one that pays the multi-second model-load cost; without it, a model loads
    lazily on its first use."""

    def __init__(self):
        self._engines: dict[str, "litert_lm.Engine"] = {}
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return litert_lm is not None

    @property
    def unavailable_reason(self) -> Optional[str]:
        return None if self.available else str(_IMPORT_ERROR)

    def _engine_for_model(self, model_key: str):
        if model_key not in self._engines:
            path = model_path(model_key)
            if not path.exists():
                raise RuntimeError(f"Model file not found: {path}")
            logger.info("Loading LLM model %r from %s", model_key, path)
            self._engines[model_key] = litert_lm.Engine(str(path))
        return self._engines[model_key]

    def warm_up(self) -> None:
        if not self.available:
            logger.warning("LLM features disabled: %s", self.unavailable_reason)
            return
        for task in EAGER_TASKS:
            model_key = TASK_MODEL.get(task)
            if not model_key:
                continue
            try:
                self._engine_for_model(model_key)
            except Exception:
                logger.exception("Failed to load model %r for task %r", model_key, task)

    def _raw_complete(
        self, task: str, prompt: str, *, system_message: Optional[str], max_output_tokens: int,
        enable_thinking: bool, response_format=None,
    ) -> str:
        if not self.available:
            raise RuntimeError(f"LLM features unavailable: {self.unavailable_reason}")
        model_key = TASK_MODEL.get(task)
        if not model_key:
            raise ValueError(f"No model configured for task {task!r}")

        engine = self._engine_for_model(model_key)
        if not enable_thinking:
            # Reasoning models (Qwen3) burn their whole token budget on a
            # <think>...</think> block before ever answering unless told not
            # to - ThinkingConfig(enable_thinking=False) alone did NOT
            # suppress it in testing, but Qwen3's documented "/no_think"
            # turn-level directive does. Kept as a system-message suffix so
            # callers don't need to know this is model-specific.
            system_message = f"{system_message}\n/no_think" if system_message else "/no_think"

        constrained_decoding_config = None
        if response_format is not None:
            constrained_decoding_config = litert_lm.ConstrainedDecodingConfig(
                enable=True, provider=litert_lm.LiteRtLmConstraintProviderType.LL_GUIDANCE,
            )

        # Serialize calls per-process - keeps this simple and safe for a
        # single-user local app rather than relying on the native lib's
        # internal concurrency guarantees across conversations.
        with self._lock:
            conversation = engine.create_conversation(
                system_message=system_message,
                max_output_tokens=max_output_tokens,
                thinking_config=litert_lm.ThinkingConfig(enable_thinking=enable_thinking),
                constrained_decoding_config=constrained_decoding_config,
            )
            try:
                response = conversation.send_message(prompt, response_format=response_format)
            finally:
                conversation.close()

        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text") or ""
                return _THINK_BLOCK.sub("", text).strip()
        return ""

    def complete(
        self, task: str, prompt: str, *, system_message: Optional[str] = None, max_output_tokens: int = 64,
        enable_thinking: bool = False,
    ) -> str:
        return self._raw_complete(
            task, prompt, system_message=system_message, max_output_tokens=max_output_tokens,
            enable_thinking=enable_thinking,
        )

    def complete_json(
        self, task: str, prompt: str, *, schema: dict[str, Any], system_message: Optional[str] = None,
        max_output_tokens: int = 150,
    ) -> dict[str, Any]:
        """Like complete(), but constrains decoding to JSON matching `schema`
        (JSON Schema dict) via the model's grammar-guided decoding - reliable
        structured output from a small model, instead of hoping it produces
        parseable JSON on its own."""
        text = self._raw_complete(
            task, prompt, system_message=system_message, max_output_tokens=max_output_tokens,
            enable_thinking=False, response_format=litert_lm.ResponseFormat.json(schema),
        )
        return json.loads(text)

    def shutdown(self) -> None:
        for engine in self._engines.values():
            try:
                engine.close()
            except Exception:
                logger.exception("Error closing LLM engine")
        self._engines.clear()


llm_router = LLMRouter()
