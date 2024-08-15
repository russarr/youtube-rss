# ruff: noqa: ERA001, S301
# TODO : del ruff ignore
# pyright: reportUnusedImport=false
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path
from pprint import pprint

from google.auth.external_account_authorized_user import Credentials as Credentials2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient import discovery

from youtube.schemas import SearchResult, Subscription, SubscriptionRequest, Video

client_secret = Path("./config/client_secret.json")


def save_credentials(credentials: Credentials | Credentials2) -> None:
    """Function to save credentials to disk"""
    _ = Path("tmp/credentials.json").write_text(credentials.to_json())


def load_credentials() -> Credentials:
    """Function to load credentials from disk"""
    with Path("tmp/credentials.json").open("r") as f:
        credentials: dict[str, str] = json.load(f)

    # обрезаем Z в timestamp, иначе при request.execute() возникает ошибка с naive date
    expiration_date = datetime.fromisoformat(credentials["expiry"].rstrip("Z"))

    return Credentials(
        token=credentials["token"],
        refresh_token=credentials["refresh_token"],
        token_uri=credentials["token_uri"],
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"],
        scopes=credentials["scopes"],
        universe_domain=credentials["universe_domain"],
        account=credentials["account"],
        expiry=expiration_date,
    )


flow = InstalledAppFlow.from_client_secrets_file(
    client_secret,
    scopes=["https://www.googleapis.com/auth/youtube.readonly"],
)
# print(flow.authorization_url()[0] + "&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2F")
# credentials = flow.run_local_server(
#     host="localhost",
#     port=8080,
#     authorization_prompt_message="Please visit this URL: {url}",
#     success_message="The auth flow is complete; you may close this window.",
#     open_browser=True,
# )
#
# save_credentials(credentials)
credentials = load_credentials()
credentials.refresh(Request())


youtube = discovery.build("youtube", "v3", credentials=credentials)


def get_subscriptions(
    youtube,  # pyright: ignore [reportMissingParameterType, reportUnknownParameterType]
    results_per_page: int = 50,
) -> list[Subscription]:
    """
    results_per_page from 0 to 50
    """

    request = (  # pyright: ignore [reportUnknownVariableType]
        youtube.subscriptions().list(
            part="snippet",
            mine=True,  # авторизация по моему аккаунту
            maxResults=results_per_page,
            order="alphabetical",
        )
    )
    response = request.execute()  # pyright: ignore [reportUnknownVariableType]
    # pprint(response)
    subsriptons_result = SubscriptionRequest.model_validate(response)
    subscriptions = subsriptons_result.items
    total_results = subsriptons_result.pageInfo.totalResults
    for _ in range(total_results // results_per_page):

        request = (  # pyright: ignore [reportUnknownVariableType]
            youtube.search().list_next(request, response)
        )

        response = request.execute()  # pyright: ignore [reportUnknownVariableType]
        subsriptons_result_batch = SubscriptionRequest.model_validate(response)
        subscriptions_batch = subsriptons_result_batch.items

        if subscriptions_batch:
            subscriptions.extend(subscriptions_batch)
    return subscriptions


subscriptions = get_subscriptions(youtube)
pprint(subscriptions[:5])

channel_id = "UC-gsAeVs_SbabaClSR5FTlw"


def get_channel_videos(
    youtube,  # pyright: ignore [reportMissingParameterType, reportUnknownParameterType]
    channel_id: str,
    results_per_page: int = 50,
) -> list[Video]:

    request = youtube.search().list(  # pyright: ignore [reportUnknownVariableType]
        part="snippet",
        channelId=channel_id,
        order="date",
        type="video",
        maxResults=results_per_page,
    )
    response = request.execute()  # pyright: ignore [reportUnknownVariableType]
    search_result = SearchResult.model_validate(response)
    total_results = search_result.pageInfo.totalResults
    videos = search_result.items
    for _ in range(total_results // results_per_page):
        request = (  # pyright: ignore [reportUnknownVariableType]
            youtube.search().list_next(
                request,
                response,
            )
        )
        response = request.execute()  # pyright: ignore [reportUnknownVariableType]
        search_result_batch = SearchResult.model_validate(response)
        videos_batch = search_result_batch.items

        if videos_batch:
            videos.extend(videos_batch)
    return videos


# get_channel_videos(youtube, "UCGWankrDBVbjUjhSR1aG-hQ")
# pprint(get_channel_videos(youtube, "UCGWankrDBVbjUjhSR1aG-hQ")[:5])
