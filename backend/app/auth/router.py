from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, get_current_user

router = APIRouter()


@router.get("/me")
async def me(current_user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, str | None]:
    return {"id": str(current_user.user_id), "email": current_user.email}
