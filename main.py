import asyncio
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from google_auth_oauthlib.flow import Flow

from config import env
from youtube.google_api_auth import (
    AuthCodeBearer,
    create_credentials_storage,
    create_flow,
)
from youtube.youtube import generate_rss_feed

app = FastAPI(title="Youtube RSS")

templates = Jinja2Templates(directory="youtube/templates")


flow = create_flow(
    ["https://www.googleapis.com/auth/youtube.readonly"],
    auth_method="code",
)
credentials_storage = create_credentials_storage(Path("tmp/credentials.json"))


@app.get("/rss")
async def rss() -> Response:
    body = await generate_rss_feed()
    return Response(content=body, media_type="application/xml")


@app.get("/")
async def index_page(request: Request) -> HTMLResponse:
    url, _ = flow.authorization_url()
    return templates.TemplateResponse("auth.jinja", {"request": request, "url": url})


@app.post("/login")
def enter_auth_code(auth_code: str = Form(...)):
    flow.fetch_token(code=auth_code)
    credentials = flow.credentials
    credentials_storage.save(credentials)
    return credentials.to_json()
    # return "OK"


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        reload=True,
        port=env.BACKEND_PORT,
        reload_excludes=[
            "db_data/*",
        ],
    )
