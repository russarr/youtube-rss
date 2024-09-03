import asyncio
from pathlib import Path

from aiohttp import web

from youtube.youtube import generate_rss_feed

async def rss(request):
    rss_feed = await generate_rss_feed()
    Path("rss_feed.xml").write_bytes(rss_feed)

    return web.Response(body=rss_feed, content_type="application/xml")


def main():
    app = web.Application()
    app.add_routes([web.get("/rss", rss)])
    web.run_app(app, port=46785)


if __name__ == "__main__":
    main()
