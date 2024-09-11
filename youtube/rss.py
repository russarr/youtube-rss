from collections import deque
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import isodate
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pymongo.database import Database

from youtube.db import read_videos_from_db_by_id_list
from youtube.exeptions import SettingsError
from youtube.schemas import VideoItem
from youtube.utils.logger import conf_logger

logger = conf_logger(__name__, "D")


xml_namespaces = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def _save_rss_deque_to_db(db: Database, rss_deque: deque) -> None:
    """Function to save deque to db"""
    logger.debug("Saving rss deque: %s to db", rss_deque)
    db.rss.update_one(
        {"_id": "rss_field"},
        {"$set": {"deque": tuple(rss_deque)}},
        upsert=True,
    )


def _load_rss_deque_from_db(db: Database, rss_len: int = 40) -> deque[str]:
    """
    Method to load deque from db. If deque not exist in db, it will return empty deque.
    """
    # TODO: add loading rss len from settings file
    logger.debug("Loading rss deque from db")
    cursor = db.rss.find_one({"_id": "rss_field"})
    rss_deque = deque(maxlen=rss_len)
    if cursor:
        video_ids = cursor["deque"]
        rss_deque.extend(video_ids)
        logger.debug("Loaded rss deque from db: %s from db", rss_deque)
    else:
        logger.debug("deque in db is not exist. Using empty deque")

    return rss_deque


def parse_video_duration(video: VideoItem) -> str:
    """Function parse video duration and return it as string"""
    if video.contentDetails is None:
        msg = (
            f"Video {video.id} has no content details field. "
            "Check that 'contentDetails' is inluded in 'part' argument for"
            "'get_videos_info_from_api' function"
        )
        logger.error(msg)
        raise SettingsError(msg)
    duration = isodate.parse_duration(video.contentDetails.duration)
    return str(timedelta(seconds=duration.total_seconds()))


def convert_description_to_html(video: VideoItem) -> str:
    """Function convert description to html to embed in rss item as html <p>"""
    html_description = []
    for line in video.snippet.description.splitlines():
        html_description.append(f"<p>{line}</p>")
    return "".join(html_description)


def local_time_filter(date: datetime, format_="<%H:%M> %d.%m.%y") -> str:
    local_tz = ZoneInfo("Asia/Yekaterinburg")
    local_dt = date.astimezone(tz=local_tz)
    local_dt.replace(tzinfo=local_tz)
    return local_dt.strftime(format_)


def _get_player_html_iframe(video: VideoItem) -> str:
    if video.player is None:
        msg = (
            f"Video {video.id} has no player field. "
            "Check that 'player' is inluded in 'part' argument for"
            "'get_videos_info_from_api' function"
        )
        logger.error(msg)
        raise SettingsError(msg)
    return video.player.embedHtml


def strip_str_from_amp(text: str) -> str:
    """Function to strip & (ampersands) from string.
    Ampersand is escaped symobol in xml.
    """
    return text.replace("&", "&amp")


def create_rss_from_template(
    videos: Iterable[VideoItem],
    template_path: Literal["rss20.jinja", "atom.jinja"],
) -> bytes:
    """Function to create rss xml from template"""
    logger.debug("Creating rss xml from template")
    env = Environment(
        loader=FileSystemLoader("youtube/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["parse_video_duration"] = parse_video_duration
    env.globals["convert_description_to_html"] = convert_description_to_html
    env.filters["local_time_filter"] = local_time_filter

    template = env.get_template(template_path)

    # TODO: вынести загрузку шаблона на самый верх в точку доступа, чтобы не читать с \
    # диска каждый раз при создании ленты

    result = template.render(
        videos=videos,
        updated=datetime.now(timezone.utc).isoformat(),
    )
    return result.encode()


def form_rss_feed_from_videos_list(db: Database, video_ids: Iterable[str]) -> bytes:
    """Function create rss 2.0 feed"""
    logger.debug("Forming rss 2.0 feed from video ids: %s", video_ids)
    rss_deque = _load_rss_deque_from_db(db)
    rss_deque.extend(video_ids)
    _save_rss_deque_to_db(db, rss_deque)

    videos = read_videos_from_db_by_id_list(db.videos, rss_deque)

    xml = create_rss_from_template(videos, "rss20.jinja")
    logger.debug("RSS feed created")
    return xml
