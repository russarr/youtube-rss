import asyncio
from collections.abc import Iterable
from datetime import datetime
from itertools import batched
from typing import Literal, Sequence

from pydantic import ValidationError

from youtube.schemas import (
    SearchResult,
    SearchResultVideo,
    Subscription,
    SubscriptionResponse,
    VideoItem,
    VideosResponse,
)
from youtube.utils.logger import conf_logger

logger = conf_logger(__name__, "E")

video_part = Literal[
    "contentDetails",
    "fileDetails",
    "id",
    "liveStreamingDetails",
    "localizations",
    "player",
    "processingDetails",
    "recordingDetails",
    "snippet",
    "statistics",
    "status",
    "suggestions",
    "topicDetails",
]

VideoDuration = Literal["any", "long", "medium", "short"]


async def get_subscriptions_from_api(
    youtube,
    part: Literal[
        "contentDetails",
        "id",
        "snippet",
        "subscriberSnippet",
    ] = "snippet",
    results_per_page: int = 50,
    order: Literal[
        "alphabetical",
        "relevance",
        "unread",
    ] = "alphabetical",
) -> set[Subscription]:
    """
    A call to this method has a quota cost of 1 unit.
    results_per_page from 0 to 50
    """
    logger.debug(
        "Getting subscriptions from api. Results per page: %s, order: %s",
        results_per_page,
        order,
    )
    subscriptions: set[Subscription] = set()
    resource = youtube.subscriptions
    request = resource().list(
        part=part,
        mine=True,  # авторизация по моему аккаунту
        maxResults=results_per_page,
        order=order,
    )
    while request is not None:
        response = await asyncio.to_thread(request.execute)
        try:
            subscriptions_result = SubscriptionResponse.model_validate(response)
        except ValidationError:
            logger.exception("Failed to validate user subscriptions loaded from api")
            raise
        subscriptions.update(subscriptions_result.items)
        request = resource().list_next(request, response)

    logger.debug("Recieved %s subscriptions from api", len(subscriptions))
    return subscriptions


async def search_videos_from_api(  # noqa: PLR0913
    youtube,
    channel_id: str,
    results_per_page: int = 50,
    order: Literal[
        "date",
        "rating",
        "relevance",
        "title",
        "videoCount",
        "viewCount",
    ] = "date",
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    duration: VideoDuration = "any",
) -> set[SearchResultVideo]:
    """
    Fucntion returns all videos from channel by channel id
    https://developers.google.com/youtube/v3/docs/search/list
    A call to this method has a quota cost of 100 units.
    param: published_before
    The value is an RFC 3339 formatted date-time value (1970-01-01T00:00:00Z).
    param: published_after
    The value is an RFC 3339 formatted date-time value (1970-01-01T00:00:00Z).
    """
    logger.debug(
        "Getting all videos from channel %s, results per page: %s",
        channel_id,
        results_per_page,
    )
    videos: set[SearchResultVideo] = set()
    additional_params = {}

    if published_after:
        additional_params["publishedAfter"] = published_after.isoformat()
    if published_before:
        additional_params["publishedAfter"] = published_before.isoformat()

    resource = youtube.search
    request = resource().list(
        part="snippet",
        channelId=channel_id,
        order=order,
        type="video",
        maxResults=results_per_page,
        videoDuration=duration,
        # **additional_params,
    )
    while request is not None:
        response = await asyncio.to_thread(request.execute)
        try:
            videos_result = SearchResult.model_validate(response)
        except ValidationError:
            logger.exception(
                "Failed to validate all videos for channel(%s) loaded from api",
                channel_id,
            )
            raise
        videos.update(videos_result.items)
        request = resource().list_next(request, response)
    return set(videos)


async def get_videos_info_from_api(
    youtube,
    video_ids: Sequence[str],
    part: Iterable[video_part] = ("contentDetails", "snippet", "player"),
) -> set[VideoItem]:
    """
    Function return video info for given video ids.
    https://developers.google.com/youtube/v3/docs/search/list
    A call to this method has a quota cost of 1 unit.
    param: part - returned video info parts
    "fileDetails", "processingDetail"s and "suggestions" are only available to that
    video's owner
    """
    logger.debug("Getting all info for videos: %s. Info parts: %s", video_ids, part)
    videos: set[VideoItem] = set()

    resource = youtube.videos
    parts = ",".join(part)

    for batch_ids in batched(video_ids, 50):

        request = resource().list(
            part=parts,
            id=",".join(batch_ids),
        )
        while request is not None:
            response = await asyncio.to_thread(request.execute)
            try:
                videos_result = VideosResponse.model_validate(response)
            except ValidationError:
                logger.exception(
                    "Failed to validate info for videos(%s) loaded from api",
                    video_ids,
                )
                raise
            videos.update(videos_result.items)
            request = resource().list_next(request, response)

    if len(videos) != len(video_ids):
        # Заметил, что иногда не совпадает, на всякий случай проверка
        msg = f"Len output result: {len(videos)}, len input vid ids: {len(video_ids)}"
        logger.error(msg)
        raise ResourceWarning(msg)
    return set(videos)
