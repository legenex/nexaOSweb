"""Focus endpoints: the operator view and the explainable ranked next-actions list.

Both are read only derivations over the live tables, scoped to the authenticated user. See
app.focus for the queries and the scoring.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.focus import build_operator_view, build_ranked_actions
from app.models.user import User
from app.schemas.focus import OperatorView, RankedActions
from app.security.auth import current_user

router = APIRouter(prefix="/focus", tags=["focus"])


@router.get("/operator", response_model=OperatorView)
def get_operator_view(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OperatorView:
    return build_operator_view(db, user)


@router.get("/ranked", response_model=RankedActions)
def get_ranked_actions(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RankedActions:
    return build_ranked_actions(db, user)
