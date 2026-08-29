from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.repositories.categories import CategoryRepository
from app.schemas import CategoryIn, CategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(include_inactive: bool = False, session: Session = Depends(get_session)):
    return CategoryRepository(session).list(include_inactive=include_inactive)


@router.post("", response_model=CategoryOut)
def add_category(payload: CategoryIn, session: Session = Depends(get_session)):
    cat = CategoryRepository(session).add(payload.name, payload.color_hex)
    session.commit()
    return cat


@router.put("/{category_id}", response_model=CategoryOut)
def rename_category(category_id: int, payload: CategoryIn, session: Session = Depends(get_session)):
    cat = CategoryRepository(session).rename(category_id, payload.name)
    if not cat:
        raise HTTPException(404, "Category not found")
    session.commit()
    return cat


@router.delete("/{category_id}")
def deactivate_category(category_id: int, session: Session = Depends(get_session)):
    cat = CategoryRepository(session).deactivate(category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    session.commit()
    return {"ok": True}


@router.put("/{category_id}/counts_as_expense", response_model=CategoryOut)
def set_counts_as_expense(category_id: int, counts_as_expense: bool, session: Session = Depends(get_session)):
    cat = CategoryRepository(session).set_counts_as_expense(category_id, counts_as_expense)
    if not cat:
        raise HTTPException(404, "Category not found")
    session.commit()
    return cat
