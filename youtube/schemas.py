# ruff: noqa: N815
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    HttpUrl,
    PlainSerializer,
    field_serializer,
)
from pydantic_core import Url

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


class VideoThumbnail(PydantModel):
    height: int
    url: HttpUrl
    width: int

    @field_serializer("url")
    def mongodb_url2str(self, val: str) -> str:
        if isinstance(val, Url):  ### This magic! If isinstance(val, HttpUrl) - error
            return str(val)
        return val


class SearchVideoThumbnails(PydantModel):
    default: VideoThumbnail
    high: VideoThumbnail
    medium: VideoThumbnail


class SearchResultVideoSnippet(PydantModel):
    channelId: str
    channelTitle: str
    description: str
    liveBroadcastContent: Literal["none", "live", "upcoming"]
    publishTime: iso_datetime
    publishedAt: iso_datetime
    thumbnails: SearchVideoThumbnails
    title: str


class SearchResultVideo(PydantModel):
    etag: str
    id: VideoId
    kind: Literal["youtube#searchResult"]
    snippet: SearchResultVideoSnippet

    def __hash__(self) -> int:
        return hash(self.id.videoId)


class PageInfoResults(PydantModel):
    resultsPerPage: int
    totalResults: int


class SearchResult(PydantModel):
    etag: str
    items: list[SearchResultVideo]
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

    @field_serializer("url")
    def mongodb_url2str(self, val: str) -> str:
        if isinstance(val, Url):  ### This magic! If isinstance(val, HttpUrl) - error
            return str(val)
        return val


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
    id: str
    etag: str
    kind: Literal["youtube#subscription"]
    snippet: SubscriptionSnippet

    def __hash__(self) -> int:
        return hash(self.snippet.channelId)


class SubscriptionResponse(PydantModel):
    etag: str
    items: list[Subscription]
    kind: Literal["youtube#SubscriptionListResponse"]
    prevPageToken: str | None = None
    nextPageToken: str | None = None
    pageInfo: PageInfoResults


class Localized(PydantModel):
    title: str
    description: str


class VideoThumbnails(PydantModel):

    default: VideoThumbnail
    high: VideoThumbnail
    medium: VideoThumbnail
    maxres: VideoThumbnail | None = None
    standard: VideoThumbnail | None = None


class VideoSnippet(PydantModel):
    publishedAt: datetime
    channelId: str
    title: str
    description: str
    thumbnails: VideoThumbnails
    channelTitle: str
    tags: list[str] | None = None
    categoryId: str
    liveBroadcastContent: str
    defaultLanguage: str | None = None
    localized: Localized
    defaultAudioLanguage: str | None = None


ContentRating = Literal[
    "acbRating",
    "agcomRating",
    "anatelRating",
    "bbfcRating",
    "bfvcRating",
    "bmukkRating",
    "catvRating",
    "catvfrRating",
    "cbfcRating",
    "cccRating",
    "cceRating",
    "chfilmRating",
    "chvrsRating",
    "cicfRating",
    "cnaRating",
    "cncRating",
    "csaRating",
    "cscfRating",
    "czfilmRating",
    "djctqRating",
    "djctqRatingReasons",
    "ecbmctRating",
    "eefilmRating",
    "egfilmRating",
    "eirinRating",
    "fcbmRating",
    "fcoRating",
    "fmocRating",
    "fpbRating",
    "fpbRatingReasons",
    "fskRating",
    "grfilmRating",
    "icaaRating",
    "ifcoRating",
    "ilfilmRating",
    "incaaRating",
    "kfcbRating",
    "kijkwijzerRating",
    "kmrbRating",
    "lsfRating",
    "mccaaRating",
    "mccypRating",
    "mcstRating",
    "mdaRating",
    "medietilsynetRating",
    "mekuRating",
    "mibacRating",
    "mocRating",
    "moctwRating",
    "mpaaRating",
    "mpaatRating",
    "mtrcbRating",
    "nbcRating",
    "nbcplRating",
    "nfrcRating",
    "nfvcbRating",
    "nkclvRating",
    "oflcRating",
    "pefilmRating",
    "rcnofRating",
    "resorteviolenciaRating",
    "rtcRating",
    "rteRating",
    "russiaRating",
    "skfilmRating",
    "smaisRating",
    "smsaRating",
    "tvpgRating",
    "ytRating",
]


class VideoContentDetailsInfo(PydantModel):
    duration: str = "PT0H0M0S"
    dimension: str
    definition: str
    caption: str
    licensedContent: bool
    regionRestriction: dict[Literal["allowed", "blocked"], list[str]] | None = None
    contentRating: dict[ContentRating, str]
    projection: str
    hasCustomThumbnail: bool | None = None


class VideoStatus(PydantModel):
    uploadStatus: str
    failureReason: str | None = None
    rejectionReason: str | None = None
    privacyStatus: str
    publishAt: datetime | None = None
    license: str
    embeddable: bool
    publicStatsViewable: bool
    madeForKids: bool
    selfDeclaredMadeForKids: bool | None = None


class VideoStatistics(PydantModel):
    """
    dislikeCount: str now deprecated
    """

    viewCount: str
    likeCount: str
    favoriteCount: str
    commentCount: str


class VideoPlayer(PydantModel):
    embedHtml: str
    embedHeight: int | None = None
    embedWidth: int | None = None


class VideoTopicDetails(PydantModel):
    topicIds: list[str] | None = None
    relevantTopicIds: list[str] | None = None
    topicCategories: list[str] | None = None


class VideoRecordingDetails(PydantModel):
    recordingDate: iso_datetime | None = None


class VideoStreams(PydantModel):
    widthPixels: int
    heightPixels: int
    frameRateFps: float
    aspectRatio: float
    codec: str
    bitrateBps: int
    rotation: str
    vendor: str


class AudioStreams(PydantModel):
    channelCount: int
    codec: str
    bitrateBps: int
    vendor: str


class VideoFileDetails(PydantModel):
    fileName: str
    fileSize: int
    fileType: str
    container: str
    videoStreams: list[VideoStreams]
    audioStreams: list[AudioStreams]
    durationMs: int
    bitrateBps: int
    creationTime: str


class VideoProcessingProgress(PydantModel):
    partsTotal: int
    partsProcessed: int
    timeLeftMs: int


class VideoTagSuggestions(PydantModel):
    tag: str
    categoryRestricts: list[str]


class VideoSuggestions(PydantModel):
    processingErrors: list[str]
    processingWarnings: list[str]
    processingHints: list[str]
    tagSuggestions: list[VideoTagSuggestions]
    editorSuggestions: list[str]


class VideoProcessingDetails(PydantModel):
    processingStatus: str
    processingProgress: VideoProcessingProgress
    processingFailureReason: str
    fileDetailsAvailability: str
    processingIssuesAvailability: str
    tagSuggestionsAvailability: str
    editorSuggestionsAvailability: str
    thumbnailsAvailability: str


class VideoLiveStreamingDetails(PydantModel):
    actualStartTime: iso_datetime
    actualEndTime: iso_datetime
    scheduledStartTime: iso_datetime | None = None
    scheduledEndTime: iso_datetime | None = None
    concurrentViewers: int | None = None
    activeLiveChatId: str | None = None


class Localization(PydantModel):
    title: str
    description: str


class VideoItem(PydantModel):
    kind: Literal["youtube#video"]
    etag: str
    id: str
    contentDetails: VideoContentDetailsInfo | None = None
    snippet: VideoSnippet
    status: VideoStatus | None = None
    statistics: VideoStatistics | None = None
    player: VideoPlayer | None = None
    topicDetails: VideoTopicDetails | None = None
    recordingDetails: VideoRecordingDetails | None = None
    fileDetails: VideoFileDetails | None = None
    processingDetails: VideoProcessingDetails | None = None
    suggestions: VideoSuggestions | None = None
    liveStreamingDetails: VideoLiveStreamingDetails | None = None
    localizations: dict[str, Localization] | None = None

    def __hash__(self) -> int:
        return hash(self.id)


class VideosResponse(PydantModel):
    kind: Literal["youtube#videoListResponse"]
    etag: str
    nextPageToken: str | None = None
    prevPageToken: str | None = None
    pageInfo: PageInfoResults
    items: list[VideoItem]
