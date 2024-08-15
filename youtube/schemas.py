# ruff: noqa: N815
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, HttpUrl, PlainSerializer

iso_datetime = Annotated[
    datetime,
    BeforeValidator(lambda x: datetime.fromisoformat(x)),  # pyright: ignore [reportAny]
    PlainSerializer(
        lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ"),  # pyright: ignore [reportAny]
    ),
]


class PydantModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoId(PydantModel):
    kind: Literal["youtube#video", "youtube#channel", "youtube#playlist"]
    videoId: str


class VidioThumbnail(PydantModel):
    height: int
    url: HttpUrl
    width: int


class VideoThumbnails(PydantModel):
    default: VidioThumbnail
    high: VidioThumbnail
    medium: VidioThumbnail


class VideoSnippet(PydantModel):
    channelId: str
    channelTitle: str
    description: str
    liveBroadcastContent: Literal["none", "live", "upcoming"]
    publishTime: iso_datetime
    publishedAt: iso_datetime
    thumbnails: VideoThumbnails
    title: str


class Video(PydantModel):
    etag: str
    id: VideoId
    kind: Literal["youtube#searchResult"]
    snippet: VideoSnippet


class PageInfoResults(PydantModel):
    resultsPerPage: int
    totalResults: int


class SearchResult(PydantModel):
    etag: str
    items: list[Video]
    kind: Literal["youtube#searchListResponse"]
    prevPageToken: str | None = None
    nextPageToken: str | None = None
    pageInfo: PageInfoResults
    regionCode: str


class SubscriptionResourseId(PydantModel):
    channelId: str
    kind: Literal["youtube#channel"]


class SubscriptionThumbnail(PydantModel):
    url: HttpUrl


class SubscriptionThumbnails(PydantModel):
    default: SubscriptionThumbnail
    high: SubscriptionThumbnail
    medium: SubscriptionThumbnail


class SubscriptionSnippet(PydantModel):
    channelId: str
    description: str
    publishedAt: iso_datetime
    resourceId: SubscriptionResourseId
    thumbnails: SubscriptionThumbnails
    title: str


class Subscription(PydantModel):
    etag: str
    id: str
    kind: Literal["youtube#subscription"]
    snippet: SubscriptionSnippet


class SubscriptionRequest(PydantModel):
    etag: str
    items: list[Subscription]
    kind: Literal["youtube#SubscriptionListResponse"]
    prevPageToken: str | None = None
    nextPageToken: str | None = None
    pageInfo: PageInfoResults
