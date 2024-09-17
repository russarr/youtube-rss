import uvicorn
from fastapi import FastAPI, Response

from config import env
from youtube.youtube import generate_rss_feed

app = FastAPI(title="Youtube RSS")


@app.get("/rss")
async def rss() -> Response:
    body = await generate_rss_feed()
    return Response(content=body, media_type="application/xml")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        reload=True,
        port=env.BACKEND_PORT,
        reload_excludes=[
            "db_data/*",
        ],
    )
