from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient import discovery

from youtube.utils.logger import conf_logger

if TYPE_CHECKING:

    from collections.abc import Iterable

    from google.auth.external_account_authorized_user import Credentials as Credentials2


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
                logger.debug("Token info file: %s is corrupted", self.storage_file)
                return None
        else:
            logger.debug("Credentials file: %s not found", self.storage_file)
            return None


ACCESS_SCOPES_ALIASES = {
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.channel-memberships.creator",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtubepartner",
    "https://www.googleapis.com/auth/youtubepartner-channel-audit",
}


class YouTubeResource1:
    """
    Class to work with YouTube API
    https://developers.google.com/identity/protocols/oauth2/scopes

    """

    def __init__(
        self,
        credentials_starage: CredentialsStorage,
        auth_method: Literal["browser", "code"] = "browser",
        access_scopes: Iterable[str] = (
            "https://www.googleapis.com/auth/youtube.readonly",
        ),
        client_secret_file: str = "./config/client_secret.json",  # noqa: S107
    ) -> None:
        self._credentials_starage = credentials_starage
        self._auth_method = auth_method
        self.access_scopes = access_scopes
        self.client_secret_file = client_secret_file

    def get_resource(self):  # noqa: ANN201
        credentials = self._get_credentials()
        return discovery.build("youtube", "v3", credentials=credentials)

    def _load_client_secret_file(self) -> Path:
        """
        https://developers.google.com/api-client-library/dotnet/guide/aaa_client_secrets
        ./config/client_secret.json
        """
        logger.debug("Load client secret file: %s", self.client_secret_file)
        client_secret = Path(self.client_secret_file)
        if not client_secret.exists():
            msg = f"Client secret file not found at: {self.client_secret_file}"
            logger.error(msg)
            raise FileNotFoundError(msg)
        return client_secret

    @staticmethod
    def _refresh_credentials(credentials: Credentials) -> Credentials:
        credentials.refresh(Request())
        return credentials

    def _get_credentials(
        self,
    ) -> Credentials | Credentials2:
        credentials = self._credentials_starage.load()
        client_secret = self._load_client_secret_file()

        if credentials:
            try:
                credentials = self._refresh_credentials(credentials)
            except RefreshError:
                logger.debug("Invalid credentials, will try to new auth")
                credentials = self._auth(client_secret)

        else:
            credentials = self._auth(client_secret)

        self._credentials_starage.save(credentials)
        return credentials

    def _auth(
        self,
        client_secret: Path,
    ) -> Credentials | Credentials2:
        match self._auth_method:
            case "browser":
                credentials = self._auth_via_browser(client_secret)
            case "code":
                credentials = self._auth_via_code(client_secret)
            case _:
                msg = f"Unknown auth method: {self._auth_method}"
                logger.error(msg)
                raise ValueError(msg)
        return credentials

    def _auth_via_browser(
        self,
        client_secret: Path,
    ) -> Credentials | Credentials2:
        """
        Function to authenticate with google API using only browser
        Access scopes: https://developers.google.com/identity/protocols/oauth2/scopes
        """
        logger.debug(
            "Auth via browser with client secret file: %s, for access scopes: %s",
            client_secret,
            self.access_scopes,
        )
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret,
            scopes=self.access_scopes,
        )

        return flow.run_local_server(
            host="localhost",
            port=8080,
            authorization_prompt_message="Please visit this URL: {url}",
            success_message="The auth flow is complete; you may close this window.",
            open_browser=True,
        )

    def _auth_via_code(
        self,
        client_secret: Path,
    ) -> Credentials | Credentials2:
        """
        Function to authenticate with google API using code
        Access scopes: https://developers.google.com/identity/protocols/oauth2/scopes
        """
        logger.debug(
            "Auth using codo with client secret file: %s, for access scopes: %s",
            client_secret,
            self.access_scopes,
        )
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret,
            scopes=self.access_scopes,
            redirect_uri="urn:ietf:wg:oauth:2.0:oob",
        )
        auth_url: tuple[str, str] = flow.authorization_url()
        url, _ = auth_url

        print(url)
        code = input("Enter code:")

        flow.fetch_token(code=code)
        return flow.credentials
