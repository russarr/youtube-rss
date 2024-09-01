import asyncio
import itertools
from collections.abc import Iterable

import aiohttp
from lxml import etree
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from youtube.db import (
    read_last_video_ids_for_channel_from_db,
    save_items_to_db,
    save_subscriptions_to_db,
)
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


async def _get_channel_rss_feed(channel_id: str) -> bytes | None:
    """Function for getting channel rss feed"""
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    logger.debug("Getting rss feed for channel %s", channel_id)
    try:
        async with aiohttp.ClientSession() as client:
            response = await client.get(rss_url)
            rss_content = await response.read()

    except aiohttp.ClientError:
        msg = f"Connection error while getting rss feed for channl {channel_id}"
        logger.exception(msg)
        raise
    logger.debug("Got rss feed for channel %s", channel_id)
    return rss_content


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
    rss_feed = await _get_channel_rss_feed(channel_id)
    rss_video_ids: tuple[str, ...] = _get_video_ids_from_rss(rss_feed)
    ids_in_db: tuple[str, ...] = read_last_video_ids_for_channel_from_db(
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


def _is_channel_new_subscription(
    ids_in_db: tuple[str, ...],
    channel_id: str,
) -> bool:
    """Function check if channel is new subscription"""
    check = len(ids_in_db) == 0
    logger.debug("Channel: %s is new subscription: %s", channel_id, check)
    return check


async def get_new_video_ids_for_all_channels(
    channel_ids: Iterable[str],
    vid_collection: Collection,
) -> tuple[str, ...]:
    """Function for getting new video ids for all channels"""
    logger.debug("Getting new video ids for all channels")
    # video_ids = []
    tasks = [
        asyncio.create_task(_get_channel_new_video_ids(channel_id, vid_collection))
        for channel_id in channel_ids
    ]
    ids = await asyncio.gather(*tasks)
    # TODO: Create exceptions
    return tuple(itertools.chain.from_iterable(ids))
    # return tuple(video_ids)


def get_channel_all_video_ids_from_api(
    youtube,
    channel_id: str,
    duration: VideoDuration = "any",
) -> tuple[str, ...]:
    """Function for getting all video ids from channel"""
    videos = search_videos_from_api(youtube, channel_id=channel_id, duration=duration)
    return tuple(i.id.videoId for i in videos)


def extract_channel_ids_from_subscriptions(
    subscriptions: Iterable[Subscription],
) -> tuple[str, ...]:
    """Function extract channel ids from subscription items"""
    logger.debug("Extracting channel ids from subscriptions")
    return tuple(s.snippet.resourceId.channelId for s in subscriptions)


async def create_video_ids_list_for_rss_feed(
    db: Database,
    youtube,
) -> tuple[str, ...]:
    subscriptions = get_subscriptions_from_api(youtube=youtube)
    save_subscriptions_to_db(db, subscriptions)
    channel_ids = extract_channel_ids_from_subscriptions(subscriptions)
    video_ids = await get_new_video_ids_for_all_channels(channel_ids, db.videos)
    videos = get_videos_info_from_api(youtube=youtube, video_ids=video_ids)

    save_items_to_db(db.videos, videos)
    return video_ids


async def generate_rss_feed() -> bytes:
    """Function to generate RSS feed"""
    logger.debug("Generating rss feed")

    client = MongoClient(
        host="127.0.0.1",
        port=27017,
        username="root",
        password="mypass",
    )
    db = client.youtube
    youtube = create_youtube_resource()

    db.subscriptions.create_index("snippet.resourceId.channelId", unique=True)
    db.videos.create_index("id", unique=True)
    db.videos.create_index("snippet.channelId")
    db.videos.create_index("snippet.publishedAt")

    video_ids = await create_video_ids_list_for_rss_feed(db, youtube)
    rss_feed = form_rss_feed_from_videos_list(db, video_ids)
    return rss_feed
