"""Auth endpoints: login / logout / check-auth."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import auth, config

router = APIRouter(tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE,
        value=token,
        max_age=config.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/login")
def login(body: LoginBody, response: Response):
    if not auth.verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = auth.create_session(body.username)
    _set_session_cookie(response, token)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/check-auth")
def check_auth(request: Request):
    token = request.cookies.get(config.SESSION_COOKIE)
    username = auth.get_token_username(token)
    if username is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"authenticated": True, "username": username}
