"""User management service rules.

Authorization invariants that must hold no matter which route or tool performs the action, so the
rule lives here at the service layer rather than only inside a single endpoint. The owner is the
highest privilege account: an admin has the same privileges as the owner except it can never delete
the owner, and the owner row can only ever be removed by the owner.
"""

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.user import User


def assert_can_delete_user(actor: User, target: User) -> None:
    """Raise if actor may not delete target.

    The owner row is protected: only the owner may remove it. Combined with the separate rule that
    no one may delete their own account, the owner row is effectively undeletable, which is the
    intended floor. An admin may manage every other account but never the owner.
    """
    if target.role == "owner" and actor.id != target.id:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "the owner account cannot be deleted by another user",
        )
