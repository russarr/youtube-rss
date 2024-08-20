import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal, Protocol, override

from google.auth.exceptions import RefreshError
from google.auth.external_account_authorized_user import Credentials as Credentials2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient import discovery

from youtube.utils.logger import conf_logger

logger = conf_logger(__name__, "D")


ScopeAliases = Literal[
    "manage_account",
    "channel_members",
    "force_ssl",
    "view_account",
    "manage_videos",
    "manage_assets",
    "audit",
]


class CredentialsStorage(Protocol):
    def save(self, token_info: Credentials | Credentials2) -> None: ...

    def load(self) -> Credentials | None: ...

    @override
    def __repr__(self) -> str: ...


class FileCredentialsStorage:
    """
    Class to save and load credentials from file
    """

    def __init__(self, storage_file: str = "./tmp/credentials.json") -> None:
        self.storage_file = Path(storage_file)
        if not self.storage_file.parent.exists():
            logger.debug(
                "There is no directory for storage file: %s. Creating.",
                self.storage_file,
            )
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def save(self, credentials: Credentials) -> None:
        """Method to save credentials to file"""
        logger.debug("Saving credentials to file: %s", self.storage_file)
        _ = self.storage_file.write_text(credentials.to_json())

    def load(self) -> Credentials | None:
        """Method to load credentials from file"""
        logger.debug("Loading credentials from file: %s", self.storage_file)
        if self.storage_file.exists():
            try:
                credentials: dict[str, str] = json.loads(self.storage_file.read_text())

                # обрезаем Z в timestamp, иначе при request.execute() возникает
                # ошибка с naive date
                expiration_date = datetime.fromisoformat(
                    credentials["expiry"].rstrip("Z"),
                )

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

            except (json.JSONDecodeError, KeyError):
                logger.debug("Credential file: %s is corrupted", self.storage_file)
                return None
        else:
            logger.debug("Credentials file: %s not found", self.storage_file)
            return None

    @override
    def __repr__(self) -> str:
        return f"FileCredentialsStorage(storage_file={self.storage_file})"


AccessScopes = Iterable[
    Literal[
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.channel-memberships.creator",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtubepartner",
        "https://www.googleapis.com/auth/youtubepartner-channel-audit",
    ]
]


def create_youtube_resource(  # noqa: ANN201
    credentials_storage: CredentialsStorage | None = None,
    auth_method: Literal["browser", "code"] = "browser",
    access_scopes: AccessScopes = ("https://www.googleapis.com/auth/youtube.readonly",),
    client_secret_file: str = "./config/client_secret.json",  # noqa: S107
):
    """
    Funtion to get main youtube api access point
    credentials_storage: where to save credentials between sessions
    auth_pipe: metod for send auth url and receive auth code
    auth_method: how to auth using only browser or manual
    access_scopes: access rights to api
    client_secret_file: path to google api client secret file
    """
    if not credentials_storage:
        logger.debug("credentials storage is not set. Creating FileCredentialsStorage")
        credentials_storage = FileCredentialsStorage()
    logger.debug("Creating youtuve api resource")
    credentials = _get_credentials(
        credentials_storage,
        client_secret_file,
        auth_method,
        access_scopes,
    )
    return discovery.build("youtube", "v3", credentials=credentials)


def _load_client_secret_file(client_secret_file: str) -> Path:
    """
    Function to load google api client secret file
    https://developers.google.com/api-client-library/dotnet/guide/aaa_client_secrets
    ./config/client_secret.json
    """
    logger.debug("Load client secret file: %s", client_secret_file)
    url = "https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid"
    client_secret = Path(client_secret_file)
    if not client_secret.exists():
        msg = f"Client secret file not found at: {client_secret_file}. Visit: {url}"
        logger.error(msg)
        raise FileNotFoundError(msg)
    return client_secret


def _refresh_credentials(credentials: Credentials) -> Credentials:
    """Function to refresh youtube api token"""
    logger.debug("refreshing credentials")
    credentials.refresh(Request())
    return credentials


def _get_saved_credentials(
    credentials_storage: CredentialsStorage,
) -> Credentials | Credentials2 | None:
    """
    Function to get youtbe credentials from storage. If saved credentials is missing
    or corrupted return None
    """
    logger.debug("Getting credentials from storage: %s", credentials_storage)
    credentials = credentials_storage.load()

    if credentials:
        logger.debug("Credentials loaded")
        try:
            credentials = _refresh_credentials(credentials)
        except RefreshError:
            logger.debug("Credentials from storage %s is invalid")

    else:
        logger.debug(
            "Credentials from storage %s not found",
            credentials_storage,
        )

    if credentials:
        credentials_storage.save(credentials)
    return credentials


def _get_credentials(
    credentials_storage: CredentialsStorage,
    client_secret_file: str,
    auth_method: Literal["browser", "code"],
    access_scopes: AccessScopes,
) -> Credentials | Credentials2 | None:
    """Function to get credentials from new auth"""
    logger.debug("Getting credentials")
    credentials = _get_saved_credentials(credentials_storage)
    if not credentials:
        logger.debug("Credentials not found, running auth method: %s", auth_method)

        auth_func_selector: dict[
            Literal["browser", "code"],
            Callable[[Path, AccessScopes], Credentials | Credentials2],
        ] = {
            "browser": _auth_via_browser,
            "code": _auth_via_code,
        }

        auth_func = auth_func_selector[auth_method]

        client_secret = _load_client_secret_file(client_secret_file)
        credentials = auth_func(client_secret, access_scopes)

    credentials_storage.save(credentials)
    return credentials


def _auth_via_browser(
    client_secret: Path,
    access_scopes: AccessScopes,
) -> Credentials | Credentials2:
    """
    Function to authenticate with google API using only browser
    Access scopes: https://developers.google.com/identity/protocols/oauth2/scopes
    """
    logger.debug(
        "Auth via browser with client secret file: %s, for access scopes: %s",
        client_secret,
        access_scopes,
    )
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret,
        scopes=access_scopes,
    )

    return flow.run_local_server(
        host="localhost",
        port=8080,
        authorization_prompt_message="Please visit this URL: {url}",
        success_message="The auth flow is complete; you may close this window.",
        open_browser=True,
    )


def _auth_via_code(
    client_secret: Path,
    access_scopes: AccessScopes,
) -> Credentials | Credentials2:
    """
    Function to authenticate with google API using code
    Access scopes: https://developers.google.com/identity/protocols/oauth2/scopes
    """
    logger.debug(
        "Auth using codo with client secret file: %s, for access scopes: %s",
        client_secret,
        access_scopes,
    )
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret,
        scopes=access_scopes,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    auth_url: tuple[str, str] = flow.authorization_url()
    url, _ = auth_url

    print(url)
    code = input("Enter code:")

    flow.fetch_token(code=code)
    return flow.credentials
