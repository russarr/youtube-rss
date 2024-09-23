from collections import deque
from collections.abc import Iterable

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pydantic import ValidationError
from pymongo import UpdateOne

from youtube.schemas import SearchResultVideo, Subscription, VideoItem
from youtube.utils.logger import conf_logger

logger = conf_logger(__name__, "D")


async def get_subscriptions_from_db(
    collection: AsyncIOMotorCollection,
) -> set[Subscription]:
    """Function retrieve set of Subscriptions from db"""
    logger.debug("Getting subscriptions from db collection: %s", collection)

    cursor = collection.find({}, {"_id": 0})

    try:
        return {Subscription.model_validate(sub) async for sub in cursor}
    except ValidationError:
        logger.exception("Failed to validate subscriptions loaded from db")
        raise


async def save_items_to_db(
    collection: AsyncIOMotorCollection,
    items: set[SearchResultVideo] | set[VideoItem],
) -> None:
    """Function to save items to db collection"""
    logger.debug("Saving %s items to db collection: %s", len(items), collection.name)
    if items:
        dump_items = (item.model_dump() for item in items)
        _ = await collection.insert_many(dump_items)


async def read_last_video_id_from_db(
    vid_collection: AsyncIOMotorCollection,
    channel_id: str,
) -> str | None:
    """Function return last video id from db. If video not in db return None"""
    last_video = (
        vid_collection.find({"snippet.channelId": channel_id}, {"_id": 0})
        .sort("snippet.publishTime", -1)
        .limit(1)
    )
    result = await last_video.to_list(1)
    if result:
        try:
            return SearchResultVideo.model_validate(result[0]).id.videoId
        except ValidationError:
            logger.exception(
                "Failed to validate last video for channel %s loaded from db",
                channel_id,
            )
            raise

    return None


async def read_channel_all_video_ids_from_db(
    vid_collection: AsyncIOMotorCollection,
    channel_id: str,
) -> set[str]:
    """Function return set of all video ids from db for given channel."""
    videos = vid_collection.find(
        {"snippet.channelId": channel_id},
        {"_id": 0, "id": 1},
        # TODO: replace 1, 0 for True False
    )
    return {vid["id"] async for vid in videos}


async def read_videos_info_from_db_by_id_list(
    vid_collection: AsyncIOMotorCollection,
    video_ids: Iterable[str],
) -> list[VideoItem]:
    """Function return list of VideoItem from db by ids list"""
    logger.debug("Read videos from db by ids list: %s", video_ids)
    res = vid_collection.find({"id": {"$in": tuple(video_ids)}}, {"_id": 0})
    try:
        return [VideoItem.model_validate(r) async for r in res]
    except ValidationError:
        logger.exception("Failed to validate videos loaded from db %s", video_ids)
        raise


async def read_last_video_ids_for_channel_from_db(
    vid_collection: AsyncIOMotorCollection,
    channel_id: str,
    limit: int = 20,
) -> tuple[str, ...]:
    """Function read last videos ids for given channel"""
    logger.debug("Reading last %s videos for channel %s from db", limit, channel_id)
    pipeline = [
        {
            "$project": {
                "_id": 0,
                "snippet.channelId": 1,
                "id": 1,
                "snippet.publishedAt": 1,
            },
        },
        {"$match": {"snippet.channelId": channel_id}},
        {"$sort": {"snippet.publishedAt": -1}},
        {"$limit": limit},
        {"$group": {"_id": 0, "ids": {"$push": "$id"}}},
    ]

    cursor = vid_collection.aggregate(pipeline)
    result = await cursor.to_list(1)
    if result:
        last_video_ids = result[0]["ids"]

        logger.debug(
            "Last video ids from db for channel  %s: %s",
            channel_id,
            last_video_ids,
        )
    else:
        logger.debug("No videos for channel %s in db", channel_id)
        last_video_ids = ()
    logger.debug(
        "Returning last video ids for channel %s: %s",
        channel_id,
        last_video_ids,
    )
    return last_video_ids


async def save_subscriptions_to_db(
    db: AsyncIOMotorDatabase,
    subscriptions: Iterable[Subscription],
) -> None:
    """
    Function to save subscriptions in db. If subscription not in db - insert it.
    Else ignore document
    """
    logger.debug("Saving subscriptions in db")
    request = [
        UpdateOne(
            filter={"snippet.resourceId.channelId": sub.snippet.resourceId.channelId},
            update={"$setOnInsert": sub.model_dump()},
            upsert=True,
        )
        for sub in subscriptions
    ]
    _ = await db.subscriptions.bulk_write(request)


async def load_rss_deque_from_db(
    db: AsyncIOMotorDatabase,
    rss_len: int = 40,
) -> deque[str]:
    """
    Method to load deque from db. If deque not exist in db, it will return empty deque.
    """
    # TODO: add loading rss len from settings file
    logger.debug("Loading rss deque from db")
    cursor = await db.rss.find_one({"_id": "rss_field"})
    rss_deque = deque(maxlen=rss_len)
    if cursor:
        video_ids = cursor["deque"]
        rss_deque.extend(video_ids)
        logger.debug("Loaded rss deque from db: %s from db", rss_deque)
    else:
        logger.debug("deque in db is not exist. Using empty deque")

    return rss_deque


async def save_rss_deque_to_db(db: AsyncIOMotorDatabase, rss_deque: deque) -> None:
    """Function to save deque to db"""
    logger.debug("Saving rss deque: %s to db", rss_deque)
    _ = await db.rss.update_one(
        {"_id": "rss_field"},
        {"$set": {"deque": tuple(rss_deque)}},
        upsert=True,
    )
