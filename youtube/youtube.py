import asyncio
import sys
from collections.abc import Iterable
from pathlib import Path

import httpx
from lxml import etree
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from config import env
from youtube.db import (
    read_last_video_ids_for_channel_from_db,
    save_items_to_db,
    save_subscriptions_to_db,
)
from youtube.exeptions import RequestError
from youtube.google_api_auth import create_youtube_resource
from youtube.rss import form_rss_feed_from_videos_list
from youtube.schemas import Subscription
from youtube.utils.logger import conf_logger
from youtube.youtube_api import (
    VideoDuration,
    get_subscriptions_from_api,
    get_videos_info_from_api,
    search_videos_from_api,
)

logger = conf_logger(__name__, "D")


async def generate_rss_feed() -> bytes:
    """Function to generate RSS feed"""
    logger.debug("Generating rss feed")

    client = AsyncIOMotorClient(
        host=env.DB_HOST,
        port=env.DB_PORT,
        username=env.MONGO_INITDB_ROOT_USERNAME,
        password=env.MONGO_INITDB_ROOT_PASSWORD,
    )
    db = client.youtube

    await db.subscriptions.create_index("snippet.resourceId.channelId", unique=True)
    await db.videos.create_index("id", unique=True)
    await db.videos.create_index("snippet.channelId")
    await db.videos.create_index("snippet.publishedAt")

    youtube = await create_youtube_resource(Path("tmp/credentials.json"))
    if youtube:
        new_video_ids = await _create_video_ids_list_for_rss_feed(db, youtube)
        logger.debug("There is %s new videos: %s", len(new_video_ids), new_video_ids)
    else:
        new_video_ids = []

    return await form_rss_feed_from_videos_list(db, new_video_ids)


def _check_if_all_requests_failed(results, exeptions) -> None:
    """Function log if all requests returned RequestError"""
    if len(exeptions) == len(results):
        logger.error(
            "All requests for rss feeds failed, check your internet connection",
        )


async def _request_channel_rss_feed(channel_id: str) -> bytes | None:
    """Function for request channel rss feed"""
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    logger.debug("Request rss feed for channel %s", channel_id)

    retry_transport = httpx.AsyncHTTPTransport(retries=3)

    try:
        async with httpx.AsyncClient(transport=retry_transport) as client:
            response = await client.get(rss_url)
            response.raise_for_status()

    except httpx.HTTPStatusError as e:
        msg = f"HTTP status error for {rss_url} {e.response}"
        logger.exception(msg)
        raise RequestError(msg) from e

    except httpx.RequestError as e:
        msg = f"Connection error for {rss_url}. Error info: {sys.exc_info()[1]}"
        logger.exception(msg)
        raise RequestError(msg) from e

    logger.debug("Got rss feed for channel %s", channel_id)
    return response.content


def _get_video_ids_from_rss(rss_feed) -> tuple[str, ...]:
    """Function parse rss feed and return video ids"""
    logger.debug("Extracting video ids from rss feed")
    rss = etree.fromstring(rss_feed)  # noqa: S320
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    video_ids = rss.xpath(
        "//atom:entry/yt:videoId/text()",
        namespaces=namespaces,
    )
    video_ids = tuple(
        str(i) for i in video_ids  # pyright: ignore [reportGeneralTypeIssues]
    )
    logger.debug("Extracted %s video ids from rss feed: %s", len(video_ids), video_ids)
    return video_ids


async def _get_channel_new_video_ids(
    channel_id: str,
    vid_collection,
) -> tuple[str, ...]:
    """Function get video ids from rss. Compared them with ids in db.
    And return only new ids"""
    logger.debug(
        "Getting only new video ids(rss exclude db) for channel %s",
        channel_id,
    )
    rss_feed = await _request_channel_rss_feed(channel_id)
    rss_video_ids: tuple[str, ...] = _get_video_ids_from_rss(rss_feed)
    ids_in_db: tuple[str, ...] = await read_last_video_ids_for_channel_from_db(
        vid_collection,
        channel_id,
    )
    new_video_ids = tuple(set(rss_video_ids) - set(ids_in_db))
    logger.debug(
        "For channel %s found %s new video ids: %s",
        channel_id,
        len(new_video_ids),
        new_video_ids,
    )
    return new_video_ids


async def _get_new_video_ids_for_all_channels(
    channel_ids: Iterable[str],
    vid_collection: AsyncIOMotorCollection,
) -> list[str]:
    """Function for getting new video ids for all channels"""
    logger.debug("Getting new video ids for all channels")

    tasks = [
        asyncio.create_task(_get_channel_new_video_ids(channel_id, vid_collection))
        for channel_id in channel_ids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    video_ids = []
    exeptions = []
    for res in results:
        if isinstance(res, RequestError):
            exeptions.append(res)
        elif isinstance(res, tuple):
            video_ids.extend(res)

    _check_if_all_requests_failed(results, exeptions)

    return video_ids


async def get_channel_all_video_ids_from_api(
    youtube,
    channel_id: str,
    duration: VideoDuration = "any",
) -> tuple[str, ...]:
    """Function for getting all video ids from channel"""
    videos = await search_videos_from_api(
        youtube,
        channel_id=channel_id,
        duration=duration,
    )
    return tuple(i.id.videoId for i in videos)


def extract_channel_ids_from_subscriptions(
    subscriptions: Iterable[Subscription],
) -> tuple[str, ...]:
    """Function extract channel ids from subscription items"""
    logger.debug("Extracting channel ids from subscriptions")
    return tuple(s.snippet.resourceId.channelId for s in subscriptions)


async def _create_video_ids_list_for_rss_feed(
    db: AsyncIOMotorDatabase,
    youtube,
) -> list[str]:
    """Function return new video ids list for generating rss feed"""
    logger.debug("Creating video ids list for rss feed")
    subscriptions = await get_subscriptions_from_api(youtube=youtube)
    _ = await save_subscriptions_to_db(db, subscriptions)
    channel_ids = extract_channel_ids_from_subscriptions(subscriptions)
    video_ids = await _get_new_video_ids_for_all_channels(channel_ids, db.videos)
    videos = await get_videos_info_from_api(youtube=youtube, video_ids=video_ids)

    _ = await save_items_to_db(db.videos, videos)
    return video_ids
