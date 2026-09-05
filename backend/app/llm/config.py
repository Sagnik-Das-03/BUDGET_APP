from pathlib import Path

from app.config import settings

# .litertlm files expected under settings.lite_llm_dir.
MODEL_FILES = {
    "qwen3_0_6b": "Qwen3-0.6B.litertlm",
    "qwen3_4b": "qwen3_4b_mixed_int4.litertlm",
    "gemma_4_e2b": "gemma-4-E2B-it-web.litertlm",
}

# Router config: which model handles which AI task. query_parse (chat query
# understanding) and summarize (monthly recap) both route to the bigger 4B
# model - in testing, the tiny 0.6B model was unreliable at multi-field
# extraction (category/range/aggregation) even with constrained decoding and
# a well-specified prompt; the two per-keystroke tasks (autocomplete,
# categorize) stay on the small model since latency matters more there than
# for a deliberate, occasional chat question or recap.
TASK_MODEL = {
    "autocomplete": "qwen3_0_6b",
    "categorize": "qwen3_0_6b",
    "query_parse": "qwen3_4b",
    "summarize": "qwen3_4b",
}

# Tasks whose model gets loaded eagerly at startup (see LLMRouter.warm_up) -
# everything else loads lazily on first use. Keeps the small, always-useful
# model warm without paying qwen3_4b's much bigger load cost on every
# startup just in case chat/recap never gets used this session.
EAGER_TASKS = {"autocomplete", "categorize"}


def model_path(model_key: str) -> Path:
    return settings.lite_llm_dir / MODEL_FILES[model_key]
