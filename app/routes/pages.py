from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.security import verify_access_key

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(verify_access_key)])
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "accounts.html",
        {
            "title": "账号信息",
        },
    )


@router.get("/accounts", response_class=HTMLResponse, dependencies=[Depends(verify_access_key)])
async def accounts(request: Request):
    return templates.TemplateResponse(
        request,
        "accounts.html",
        {
            "title": "账号信息",
        },
    )
