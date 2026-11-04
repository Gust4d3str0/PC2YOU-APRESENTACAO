from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from settings import Settings, get_settings


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: int


def _unauthorized(detail: str = "Token de acesso inválido") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="Autenticação não configurada no serviço")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Token Bearer obrigatório")

    decode_options = {"require": ["sub", "exp"]}
    decode_kwargs = {}
    if settings.jwt_audience:
        decode_kwargs["audience"] = settings.jwt_audience
    else:
        decode_options["verify_aud"] = False

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options=decode_options,
            **decode_kwargs,
        )
        subject = payload["sub"]
        user_id = int(subject)
        if isinstance(subject, bool) or user_id <= 0 or str(user_id) != str(subject):
            raise ValueError("invalid subject")
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise _unauthorized()

    return AuthenticatedUser(user_id=user_id)


def require_payload_owner(payload_user_id: int, current_user: AuthenticatedUser) -> None:
    if payload_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="O user_id deve corresponder ao token de acesso")
