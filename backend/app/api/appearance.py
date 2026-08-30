from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db import get_session
from app.repositories.app_settings import AppSettingRepository

router = APIRouter(prefix="/api/appearance", tags=["appearance"])

# Same colors as the frontend's lib/palette.ts defaults - kept in sync manually
# since this is the fallback for a chart color the user hasn't customized yet.
# Validated with the dataviz skill's validate_palette.js against both the light
# (#fcfcfb) and dark (#1c1b19) chart surfaces: lightness band, chroma floor,
# adjacent CVD separation (>=8 target), normal-vision floor, and contrast all
# PASS as one set in both modes, so no separate dark-mode steps are needed.
DEFAULT_PALETTE = {
    "income": "#3B82F6",
    "expenses": "#F43F5E",
    "net": "#6366F1",
    "goal": "#898781",
    "sip": "#D97706",
    "cash_savings": "#0D9488",
}
PALETTE_SETTING_KEYS = {name: f"palette.{name}" for name in DEFAULT_PALETTE}


class PaletteIn(BaseModel):
    income: Optional[str] = None
    expenses: Optional[str] = None
    net: Optional[str] = None
    goal: Optional[str] = None
    sip: Optional[str] = None
    cash_savings: Optional[str] = None


def _current_palette(session: Session) -> dict:
    repo = AppSettingRepository(session)
    return {name: repo.get(key) or DEFAULT_PALETTE[name] for name, key in PALETTE_SETTING_KEYS.items()}


@router.get("/palette")
def get_palette(session: Session = Depends(get_session)):
    return _current_palette(session)


@router.put("/palette")
def set_palette(payload: PaletteIn, session: Session = Depends(get_session)):
    repo = AppSettingRepository(session)
    for name, value in payload.model_dump(exclude_none=True).items():
        repo.set(PALETTE_SETTING_KEYS[name], value)
    session.commit()
    return _current_palette(session)


@router.delete("/palette")
def reset_palette(session: Session = Depends(get_session)):
    repo = AppSettingRepository(session)
    for key in PALETTE_SETTING_KEYS.values():
        repo.clear(key)
    session.commit()
    return dict(DEFAULT_PALETTE)
