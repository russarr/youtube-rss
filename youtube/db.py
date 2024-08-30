from collections.abc import Iterable

from pymongo import UpdateOne
from pymongo.collection import Collection
from pymongo.database import Database

from youtube.schemas import SearchResultVideo, Subscription, VideoItem
from youtube.utils.logger import conf_logger

logger = conf_logger(__name__, "D")


def get_subscriptions_from_db(collection: Collection) -> set[Subscription]:
    """Function retrieve set of Subscriptions from db"""
    logger.debug("Getting subscriptions from db collection: %s", collection)

    subscriptions = collection.find({}, {"_id": 0})
    return {Subscription.model_validate(sub) for sub in subscriptions}


def save_items_to_db(
    collection: Collection,
    items: set[SearchResultVideo] | set[VideoItem],
) -> None:
    """Function to save items to db collection"""
    logger.debug("Saving %s items to db collection: %s", len(items), collection.name)
    if items:
        dump_items = (item.model_dump() for item in items)
        _ = collection.insert_many(dump_items)


def read_last_video_id_from_db(
    vid_collection: Collection,
    channel_id: str,
) -> str | None:
    """Function return last video id from db. If video not in db return None"""
    last_video = (
        vid_collection.find({"snippet.channelId": channel_id}, {"_id": 0})
        .sort("snippet.publishTime", -1)
        .limit(1)
    )
    result = tuple(last_video)
    if result:
        return SearchResultVideo.model_validate(result[0]).id.videoId
    return None


def read_channel_all_video_ids_from_db(
    vid_collection: Collection,
    channel_id: str,
) -> set[str]:
    """Function return set of all video ids from db for given channel."""
    videos = vid_collection.find({"snippet.channelId": channel_id}, {"_id": 0, "id": 1})
    return {vid["id"] for vid in videos}


def read_videos_from_db_by_id_list(
    vid_collection: Collection,
    video_ids: Iterable[str],
) -> tuple[VideoItem, ...]:
    """Function return list of VideoItem from db by ids list"""
    logger.debug("Read videos from db by ids list: %s", video_ids)
    res = vid_collection.find({"id": {"$in": tuple(video_ids)}}, {"_id": 0})
    return tuple(VideoItem.model_validate(r) for r in res)


def read_last_video_ids_for_channel_from_db(
    vid_collection: Collection,
    channel_id: str,
    limit: int = 20,
) -> tuple[str, ...]:
    """Function read last videos ids for given channel"""
    logger.debug("Read last %s videos for channel %s from db", limit, channel_id)
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
    result = cursor.try_next()
    if result:
        last_video_ids = result["ids"]
        logger.debug("Last video ids for channel %s: %s", channel_id, last_video_ids)
    else:
        logger.debug("No videos for channel %s in db", channel_id)
        last_video_ids = ()
    logger.debug(
        "Returning last video ids for channel %s: %s",
        channel_id,
        last_video_ids,
    )
    return last_video_ids


def save_subscriptions_to_db(
    db: Database,
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
    db.subscriptions.bulk_write(request)
