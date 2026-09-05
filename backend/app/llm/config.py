from pathlib import Path

from app.config import settings

# .litertlm files expected under settings.lite_llm_dir.
MODEL_FILES = {
    "qwen3_0_6b": "Qwen3-0.6B.litertlm",
    "qwen3_4b": "qwen3_4b_mixed_int4.litertlm",
    "gemma_4_e2b": "gemma-4-E2B-it-web.litertlm",
}

# Router config: which model handles which AI task. Only the models
# referenced here get loaded (see LLMRouter.warm_up) - add a task/model pair
# as new features are built, e.g. "summarize": "qwen3_4b" for a heavier task
# that can tolerate a slower, higher-quality model.
TASK_MODEL = {
    "autocomplete": "qwen3_0_6b",
}


def model_path(model_key: str) -> Path:
    return settings.lite_llm_dir / MODEL_FILES[model_key]
