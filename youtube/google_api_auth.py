import asyncio
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, Protocol, override

from google.auth.exceptions import RefreshError
from google.auth.external_account_authorized_user import Credentials as Credentials2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient import discovery
from googleapiclient.discovery import Resource
from motor.motor_asyncio import AsyncIOMotorCollection

from youtube.exeptions import SettingsError
from youtube.utils.logger import conf_logger

logger = conf_logger(__name__, "D")


CLIENT_SECRET_PATH: Final = "config/client_secret.json"

ScopeAliases = Literal[
    "manage_account",
    "channel_members",
    "force_ssl",
    "view_account",
    "manage_videos",
    "manage_assets",
    "audit",
]
# TODO: check if aliases needed

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


async def ainput(prompt: str) -> str:
    """Function to run async console input"""
    return await asyncio.to_thread(input, f"{prompt} ")


class CredentialsStorage(Protocol):
    # TODO: сделать асинхронным
    def save(self, credentials: Credentials | Credentials2) -> None: ...

    def load(self) -> Credentials | None: ...

    @override
    def __repr__(self) -> str: ...


class FileCredentialsStorage:
    """
    Class to save and load credentials from file
    """

    # TODO: сделать асинхронным

    def __init__(self, storage_file: Path) -> None:
        self.storage_file = storage_file
        if not self.storage_file.parent.exists():
            logger.debug(
                "There is no directory for storage file: %s. Creating.",
                self.storage_file,
            )
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def save(self, credentials: Credentials | Credentials2) -> None:
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


class DBCredentialsStorage:
    """Class to save and load credentials from database"""

    def __init__(self, storage_access_point: AsyncIOMotorCollection) -> None:
        self._col = storage_access_point

    def save(self, credentials: Credentials | Credentials2) -> None:
        raise NotImplementedError

    def load(self) -> Credentials | None:
        raise NotImplementedError

    @override
    def __repr__(self) -> str:
        # TODO: не забыть исправить repr
        return "DBCredentialsStorage(credentials={self.credentials})"


class AuthCodeBearer:
    """Class to transfer auth url and code between coroutines"""

    def __init__(self) -> None:
        self.code: str | None = None
        self.url: str | None = None


class AuthPipe(Protocol):
    def send(self, auth_url: str) -> None: ...

    async def receive(self) -> str: ...


class ConsoleAuthPipe:
    """Class to send auth url and receive auth code through console"""

    def send(self, auth_url: str) -> None:
        print(f"Visit: {auth_url} then print auth code to console")

    async def receive(self) -> str:
        return await ainput("Enter google auth code:")


class TelegramAuthPipe:
    """Class to send auth url and receive auth code through Telegram bot"""

    def send(self, auth_url: str) -> None:
        raise NotImplementedError

    def receive(self) -> str:
        raise NotImplementedError


class WebAuthPipe:
    """Class to send auth url and receive auth code through web browser"""

    def __init__(self, auth_code_bearer: AuthCodeBearer, event: asyncio.Event) -> None:
        self._auth_code_bearer = auth_code_bearer
        self._event = event

    def send(self, auth_url: str) -> None:
        self._auth_code_bearer.url = auth_url

    async def receive(self) -> str:
        await self._event.wait()

        if self._auth_code_bearer.code:
            return self._auth_code_bearer.code

        msg = "Auth code is not recieved"
        logger.error(msg)
        raise AttributeError(msg)


def _is_credentials_fresh(credentials: Credentials) -> bool:
    """Function checking whether credentials are expired

    Args:
        credentials (Credentials): credentials to check

    Returns:
        bool: True if credentials are not expired
    """
    logger.debug("Credentils state: %s", credentials.token_state.name)
    if is_fresh := (credentials.token_state.name == "FRESH"):
        logger.debug("Credentials are expired, is fresh: %s", is_fresh)
    else:
        logger.debug("Credentials are not expired, is fresh: %s", is_fresh)
    return is_fresh


def create_credentials_storage(
    storage_access_point: Path | AsyncIOMotorCollection,
) -> CredentialsStorage:
    """
    Function to create credentials storage

    Args:
        storage_access_point (Path | AsyncIOMotorCollection): path to credentials
            file or collection in database
    Returns:
        CredentialsStorage
    """
    logger.debug(
        "Creating credentials storage, with access point %s",
        storage_access_point,
    )
    match storage_access_point:
        case Path():
            storage = FileCredentialsStorage(storage_access_point)
        case AsyncIOMotorCollection():
            storage = DBCredentialsStorage(storage_access_point)

    logger.debug("Credentials storage: %s created", storage)
    return storage


def create_auth_pipe(
    pipe_type: Literal["console", "telegram", "web"],
    auth_code_bearer: AuthCodeBearer | None = None,
    event: asyncio.Event | None = None,
) -> AuthPipe:
    """
    Function to create auth pipe for sending auth url and receiving auth code

    Args:
        pipe_type(str): type of auth pipe:
            console: url prints in console, auth code reciving through input
            #TODO: add telegram param desription to docstring
            telegram: ...
            web: url and code transfred through auth_code_bearer, using asyncio event
        auth_code_bearer(AuthCodeBearer): class to transfer auth url and code between
            coroutines
        event(asyncio.Event): asyncio event

    Returns:
        Instanse of AuthPipe

    Raises:
        SettingsError: if auth pipe is web or telegram, auth_code_bearer and event are
        mandatory parameters
    """
    logger.debug(
        "Creating auth pipe: %s with params: auth_code_bearer:%s, event:%s",
        pipe_type,
        auth_code_bearer,
        event,
    )
    match pipe_type:
        case "console":
            return ConsoleAuthPipe()
        case "telegram":
            raise NotImplementedError
        case "web":
            if auth_code_bearer and event:
                return WebAuthPipe(auth_code_bearer, event)
            msg = "web auth pipe requires auth_code_bearer and event"
            logger.error(msg)
            raise SettingsError(msg)


async def create_youtube_resource(
    storage_access_point: Path | AsyncIOMotorCollection,
) -> Resource | None:
    """
    Funtion to get main youtube api access point

    Args:
        credentials (Credentials): credentials
    Returns:
        Resource: youtube api access point
    """
    logger.debug("Creating youtube api resource")
    credentials_storage = create_credentials_storage(storage_access_point)
    credentials = credentials_storage.load()
    if credentials and _is_credentials_fresh(credentials):
        credentials = await _refresh_credentials(credentials)
        credentials_storage.save(credentials)

        logger.debug("Youtube api resource created")
        return discovery.build("youtube", "v3", credentials=credentials)

    logger.debug("youtube api resource not created")
    return None


def _load_client_secret_file(client_secret_file: str) -> Path:
    """
    Function to load google api client secret file
    https://developers.google.com/api-client-library/dotnet/guide/aaa_client_secrets
    ./config/client_secret.json
    """
    logger.debug("Load client secret file: %s", client_secret_file)
    url = (
        "https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid"
    )
    client_secret = Path(client_secret_file)
    if not client_secret.exists():
        msg = f"Client secret file not found at: {client_secret_file}. Visit: {url}"
        logger.error(msg)
        raise FileNotFoundError(msg)
    return client_secret


async def _refresh_credentials(credentials: Credentials) -> Credentials:
    """Function to refresh youtube api token"""
    logger.debug("refreshing credentials")
    try:
        await asyncio.to_thread(credentials.refresh, Request())
    except RefreshError:
        logger.exception("Failed to refresh credentials")
        raise
    return credentials


def load_saved_credentials(
    storage_access_point: Path | AsyncIOMotorCollection,
) -> Credentials | None:
    """
    Function to get youtbe credentials from storage.

    Args:
        storage_access_point (Path | AsyncIOMotorCollection): path to credentials
            file or collection in database
    Returns:
        Credentials
    """
    logger.debug(
        "Loading credentials from storage with access point: %s",
        storage_access_point,
    )
    credentials_storage = create_credentials_storage(storage_access_point)
    credentials = credentials_storage.load()

    if credentials:
        logger.debug("Credentials from storage: %s loaded", credentials_storage)
    else:
        logger.debug(
            "Credentials from storage: %s not found",
            credentials_storage,
        )
    return credentials


async def get_new_credentials(
    credentials_storage: CredentialsStorage,
    client_secret_file_path: str,
    app_type: Literal["local", "web"],
    access_scopes: AccessScopes,
    auth_pipe: AuthPipe,
) -> Credentials | Credentials2:
    logger.debug("Credentials not found, running auth method: %s", app_type)
    client_secret = _load_client_secret_file(client_secret_file_path)

    credentials_storage = create_credentials_storage(Path("tmp/credentials.json"))
    match app_type:
        case "local":
            credentials = _auth_as_local_app(client_secret, access_scopes)
        case "web":
            credentials = await _auth_web_with_code(
                client_secret,
                access_scopes,
                auth_pipe,
            )
    credentials_storage.save(credentials)
    return credentials


def _auth_as_local_app(
    client_secret: Path,
    access_scopes: AccessScopes,
) -> Credentials | Credentials2:
    """
    Function to authenticate with google API using local browser
    Suitable only when starting on a local PC
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

    # TODO: check bind_addr: Unknown | None = None, how to use

    return flow.run_local_server(
        host="localhost",
        port=8080,
        authorization_prompt_message="Please visit this URL: {url}",
        success_message="The auth flow is complete; you may close this window.",
        open_browser=True,
    )


async def _auth_web_with_code(
    client_secret: Path,
    access_scopes: AccessScopes,
    auth_pipe: AuthPipe,
) -> Credentials | Credentials2:
    """
    Function to authenticate with google API using code
    Access scopes: https://developers.google.com/identity/protocols/oauth2/scopes
    """
    logger.debug(
        "Auth using code with client secret file: %s, for access scopes: %s",
        client_secret,
        access_scopes,
    )
    flow = Flow.from_client_secrets_file(
        client_secret,
        scopes=access_scopes,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    auth_url: tuple[str, str] = flow.authorization_url()
    url, _ = auth_url

    auth_pipe.send(url)
    logger.debug("url is sended to bearer")
    code = await auth_pipe.receive()

    flow.fetch_token(code=code)
    return flow.credentials


def create_flow(
    access_scopes: AccessScopes,
    auth_method: Literal["code", "redirect"],
) -> Flow:
    """
    Function to create google auth flow

    Args:
        access_scopes (AccessScopes): list of access scopes
        ath_method (Literal["code", "redirect"]): auth method
    Returns:
        Flow
    """
    logger.debug("Creating flow for access scopes: %s", access_scopes)
    if auth_method == "code":
        redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    else:
        # TODO: implement redirect case
        raise NotImplementedError

    # TODO: add client secret path to env

    return Flow.from_client_secrets_file(
        _load_client_secret_file(CLIENT_SECRET_PATH),
        scopes=access_scopes,
        redirect_uri=redirect_uri,
    )
