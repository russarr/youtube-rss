from collections import deque
from collections.abc import Iterable

from lxml import etree
from lxml.etree import Element, QName, SubElement, _Element
from pymongo.database import Database

from youtube.db import read_videos_from_db_by_id_list
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


def create_rss_header() -> _Element:
    """Function create header and root element for RSS.
    Return lxml root Element"""
    feed = Element("feed", nsmap=xml_namespaces)
    SubElement(feed, "title").text = "My rss channel name"
    author = SubElement(feed, "author")
    SubElement(author, "name").text = "russarr"
    # TODO: set my links
    SubElement(
        feed,
        "link",
        rel="self",
        href="https://www.youtube.com/feeds/videos.xml",
    )
    SubElement(
        feed,
        "link",
        rel="alternate",
        href="https://www.youtube.com/feeds/videos.xml",
    )
    SubElement(feed, "published").text = "2022-01-01T00:00:00+00:00"
    # TODO: rss channel image
    """
       <image>
        <url>https://www.yaplakal.com/html/static/top-logo.png</url>
        <title>ЯПлакалъ - развлекательное сообщество</title>
        <link>https://www.yaplakal.com</link>
       </image>

    """
    return feed


def create_rss_item_entry_for_video(video: VideoItem) -> _Element:
    """Function create rss item entry for video.
    Return lxml entry Element"""
    entry = Element("entry")
    SubElement(entry, "id").text = f"yt:video:{video.id}"
    SubElement(entry, QName(xml_namespaces["yt"], "videoId")).text = video.id
    SubElement(entry, QName(xml_namespaces["yt"], "channelId")).text = (
        video.snippet.channelId
    )
    SubElement(entry, "title").text = video.snippet.title
    SubElement(entry, "published").text = video.snippet.publishedAt.isoformat()

    video_link = f"https://www.youtube.com/watch?v={video.id}"
    SubElement(entry, "link", rel="alternate", href=video_link)

    author = SubElement(entry, "author")
    SubElement(author, "name").text = video.snippet.channelTitle

    author_url = f"https://www.youtube.com/channel/{video.snippet.channelId}"
    SubElement(author, "uri").text = author_url


    media = SubElement(entry, QName(xml_namespaces["media"], "group"))
    SubElement(media, QName(xml_namespaces["media"], "title")).text = (
        video.snippet.title
    )
    SubElement(
        media,
        QName(xml_namespaces["media"], "content"),
        attrib={
            "url": f"https://www.youtube.com/v/{video.id}?version=3",
            "type": "application/x-shockwave-flash",
            "width": "640",
            "height": "390",
        },
    )
    SubElement(
        media,
        QName(xml_namespaces["media"], "thumbnail"),
        attrib={
            "url": str(
                video.snippet.thumbnails.default.url,
            ),  # TODO: check thumbnail type
            "width": "480",
            "height": "360",
        },
    )
    SubElement(media, QName(xml_namespaces["media"], "description")).text = (
        video.snippet.description
    )
    return entry


def form_rss_feed_from_videos_list(db: Database, video_ids: Iterable[str]) -> bytes:
    """Function create rss feed"""
    logger.debug("Forming rss feed from video ids: %s", video_ids)
    rss_deque = _load_rss_deque_from_db(db)
    rss_deque.extend(video_ids)
    _save_rss_deque_to_db(db, rss_deque)

    videos = read_videos_from_db_by_id_list(db.videos, rss_deque)

    feed = create_rss_header()
    for video in videos:
        entry = create_rss_item_entry_for_video(video)
        feed.append(entry)
    return etree.tostring(  # pyright: ignore [reportAttributeAccessIssue]
        feed,
        xml_declaration=True,
        encoding="utf-8",
    )


if __name__ == "__main__":
    res = create_rss_header()
    res = etree.tostring(res, xml_declaration=True, encoding="utf-8")
    print(res.decode("utf-8"))
