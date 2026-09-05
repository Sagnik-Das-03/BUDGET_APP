from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.llm.router import llm_router
from app.repositories.transactions import TransactionRepository
from app.schemas import AutocompleteIn, AutocompleteOut

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status")
def llm_status():
    return {"available": llm_router.available, "reason": llm_router.unavailable_reason}


@router.post("/autocomplete", response_model=AutocompleteOut)
def autocomplete(payload: AutocompleteIn, session: Session = Depends(get_session)):
    text = payload.text.strip()
    if not text:
        return AutocompleteOut(suggestion="")

    seen: list[str] = []
    for desc in TransactionRepository(session).recent_descriptions(limit=300):
        if desc not in seen:
            seen.append(desc)
        if len(seen) >= 200:
            break

    # A past description sharing this prefix is a better bet than any LLM guess.
    prefix_matches = [d for d in seen if d.lower() != text.lower() and d.lower().startswith(text.lower())]
    if prefix_matches:
        return AutocompleteOut(suggestion=prefix_matches[0])

    if not llm_router.available or len(text) < 2:
        return AutocompleteOut(suggestion="")

    examples = "\n".join(f"- {d}" for d in seen[:20])
    prompt = (
        f"Past transaction descriptions from this user (most recent first):\n{examples}\n\n"
        f'Complete this partial transaction description in the same style: "{text}"\n'
        "Reply with ONLY the completed description, nothing else."
    )
    try:
        suggestion = llm_router.complete(
            "autocomplete", prompt,
            system_message="You autocomplete short transaction descriptions for a personal budget tracker app. Be concise.",
            max_output_tokens=24,
        )
    except Exception:
        return AutocompleteOut(suggestion="")

    suggestion = suggestion.strip().strip('"')
    if not suggestion or suggestion.lower() == text.lower() or not suggestion.lower().startswith(text.lower()):
        return AutocompleteOut(suggestion="")
    return AutocompleteOut(suggestion=suggestion)
