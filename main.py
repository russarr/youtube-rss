import asyncio

from youtube.youtube import generate_rss_feed


async def main() -> None:
    rss_feed = await generate_rss_feed()
    print(rss_feed.decode("utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
