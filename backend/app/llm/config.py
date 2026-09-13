from pathlib import Path

from app.config import settings

# .litertlm files expected one per subfolder under settings.lite_llm_dir,
# named after the model key (e.g. models/qwen3_4b/qwen3_4b_mixed_int4.litertlm)
# - each model's own generated cache files (.xnnpack_cache, mldrift_*.bin,
# named after its .litertlm file and written alongside it) live in that same
# subfolder rather than all models' caches being dumped flat together, which
# got hard to tell apart as more models were added.
MODEL_FILES = {
    "qwen3_0_6b": "Qwen3-0.6B.litertlm",
    "qwen3_4b": "qwen3_4b_mixed_int4.litertlm",
    "deepseek_r1": "DeepSeek-R1-Distill-Qwen-1.5B_multi-prefill-seq_q8_ekv4096.litertlm",
    "smol_lm2": "SmolLM2_360M_instruct.litertlm",
}

# Human-readable names for the UI (e.g. "which model is answering this?").
MODEL_DISPLAY_NAMES = {
    "qwen3_0_6b": "Qwen3 0.6B",
    "qwen3_4b": "Qwen3 4B (int4)",
    "deepseek_r1": "Deepseek-R1",
    "smol_lm2": "SmolLM2"
}

# Router config: which model handles which AI task. query_parse (chat query
# understanding) and summarize (monthly recap) both route to the bigger 4B
# model - in testing, the tiny 0.6B model was unreliable at multi-field
# extraction (category/range/aggregation) even with constrained decoding and
# a well-specified prompt; the two per-keystroke tasks (autocomplete,
# categorize) each stay on a small model since latency matters more there
# than for a deliberate, occasional chat question or recap.
TASK_MODEL = {
    "autocomplete": "smol_lm2",
    "categorize": "qwen3_0_6b",
    "suggest_view_name": "qwen3_0_6b",
    "query_parse": "qwen3_4b",
    "summarize": "qwen3_4b",
    "quick_add": "qwen3_4b",
}

# Tasks whose model gets loaded eagerly at startup (see LLMRouter.warm_up) -
# everything else loads lazily on first use. Keeps the small, always-useful
# model warm without paying qwen3_4b's much bigger load cost on every
# startup just in case chat/recap never gets used this session.
EAGER_TASKS = {"autocomplete", "categorize"}


def model_path(model_key: str) -> Path:
    return settings.lite_llm_dir / model_key / MODEL_FILES[model_key]
