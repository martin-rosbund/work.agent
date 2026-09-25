from fastapi import APIRouter, Request, Response

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service
from .schemas import Login

router = APIRouter(tags=["auth"])
PREFIX = "/api/v1"


@router.get(PREFIX + "/auth/status", response_model=AuthStatus)
def auth_status(request: Request, db=DB):
    return service.auth_status(request=request, db=db)


@router.post(PREFIX + "/auth/setup", response_model=SessionCreated)
def setup(body: Login, request: Request, response: Response, db=DB):
    return service.setup(body=body, request=request, response=response, db=db)


@router.post(PREFIX + "/auth/login", response_model=SessionCreated)
def login(body: Login, request: Request, response: Response, db=DB):
    return service.login(body=body, request=request, response=response, db=db)


@router.post(PREFIX + "/auth/logout", response_model=Ok)
def logout(response: Response, session=Auth, db=DB):
    return service.logout(response=response, session=session, db=db)
