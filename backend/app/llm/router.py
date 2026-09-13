import json
import logging
import re
import threading
from typing import Any, Optional

from app.config import settings
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
        # Whichever backend actually ended up serving each model - not
        # necessarily settings.llm_backend, since a GPU engine that fails at
        # inference time gets swapped for a CPU one for the rest of the
        # process (see _raw_complete's fallback). Exposed via backend_for()
        # so callers (e.g. the benchmark script) can see when that happened.
        self._engine_backend: dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return litert_lm is not None

    @property
    def unavailable_reason(self) -> Optional[str]:
        return None if self.available else str(_IMPORT_ERROR)

    def backend_for(self, model_key: str) -> Optional[str]:
        return self._engine_backend.get(model_key)

    def _create_engine(self, path, backend: str):
        native_backend = litert_lm.Backend.GPU() if backend == "gpu" else litert_lm.Backend.CPU()
        return litert_lm.Engine(str(path), backend=native_backend)

    def _engine_for_model(self, model_key: str, backend: Optional[str] = None):
        """Returns the cached engine for this model, (re)creating it if
        there's none yet or the requested backend differs from whichever one
        is currently cached (the GPU-failed-so-fall-back-to-CPU path)."""
        backend = backend or settings.llm_backend
        if model_key in self._engines and self._engine_backend.get(model_key) == backend:
            return self._engines[model_key]

        path = model_path(model_key)
        if not path.exists():
            raise RuntimeError(f"Model file not found: {path}")
        logger.info("Loading LLM model %r from %s (backend=%s)", model_key, path, backend)
        try:
            engine = self._create_engine(path, backend)
        except Exception:
            # GPU engine CREATION failing outright is the easy case to catch
            # here - the harder one (creation succeeds, later send_message()
            # calls fail) is handled per-call in _raw_complete instead, since
            # construction alone can't detect it.
            if backend == "gpu":
                logger.exception("GPU engine creation failed for %r - falling back to CPU", model_key)
                engine = self._create_engine(path, "cpu")
                backend = "cpu"
            else:
                raise

        old = self._engines.get(model_key)
        if old is not None and old is not engine:
            try:
                old.close()
            except Exception:
                logger.exception("Error closing previous engine for %r", model_key)
        self._engines[model_key] = engine
        self._engine_backend[model_key] = backend
        return engine

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

    def is_loaded(self, task: str) -> bool:
        """Whether the model backing `task` has already been loaded into
        memory - lets a caller (e.g. the Ask page) show a "loading model"
        state up front instead of the first real question silently taking
        up to a minute."""
        model_key = TASK_MODEL.get(task)
        return bool(model_key) and model_key in self._engines

    def warm_up_task(self, task: str) -> None:
        """Eagerly load the model for one task on demand, outside the fixed
        EAGER_TASKS set - e.g. triggered from the frontend the moment a user
        opens a chat-style page, rather than waiting for their first message."""
        if not self.available:
            raise RuntimeError(f"LLM features unavailable: {self.unavailable_reason}")
        model_key = TASK_MODEL.get(task)
        if not model_key:
            raise ValueError(f"No model configured for task {task!r}")
        self._engine_for_model(model_key)

    def _send_message(self, engine, prompt: str, *, system_message, max_output_tokens: int,
                       enable_thinking: bool, constrained_decoding_config, response_format):
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
                return conversation.send_message(prompt, response_format=response_format)
            finally:
                conversation.close()

    def _raw_complete(
        self, task: str, prompt: str, *, system_message: Optional[str], max_output_tokens: int,
        enable_thinking: bool, response_format=None,
    ) -> str:
        if not self.available:
            raise RuntimeError(f"LLM features unavailable: {self.unavailable_reason}")
        model_key = TASK_MODEL.get(task)
        if not model_key:
            raise ValueError(f"No model configured for task {task!r}")

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

        engine = self._engine_for_model(model_key)
        try:
            response = self._send_message(
                engine, prompt, system_message=system_message, max_output_tokens=max_output_tokens,
                enable_thinking=enable_thinking, constrained_decoding_config=constrained_decoding_config,
                response_format=response_format,
            )
        except Exception:
            if self._engine_backend.get(model_key) != "gpu":
                raise
            # The documented GPU failure mode: engine CREATION succeeded but
            # this actual inference call failed outright. Retry once on a
            # fresh CPU engine for this model - _engine_for_model() replaces
            # the cached GPU engine with it, so every later call for this
            # model skips GPU entirely instead of paying this failure again.
            logger.exception("GPU inference failed for model %r - falling back to CPU", model_key)
            engine = self._engine_for_model(model_key, backend="cpu")
            response = self._send_message(
                engine, prompt, system_message=system_message, max_output_tokens=max_output_tokens,
                enable_thinking=enable_thinking, constrained_decoding_config=constrained_decoding_config,
                response_format=response_format,
            )

        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text") or ""
                text = _THINK_BLOCK.sub("", text).strip()
                # U+FFFD shows up when the native decoder's output was cut
                # mid multi-byte UTF-8 sequence (e.g. an em dash split across
                # a token boundary) - never surface that mangled glyph to a user.
                return text.replace("�", "-")
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
