"""
googleapiclient.errors.HttpError: <HttpError 403 when requesting https://youtube.googleapis.com/youtube/v3/videos?part=contentDetails&id=aOly5eEDXug%2CDvdZv_DD0DY&alt=json returned "The request cannot be completed because you have exceeded your <a href="/youtube/v3/getting-started#quota">quota</a>.". Details: "[{'message': 'The request cannot be completed because you have exceeded your <a href="/youtube/v3/getting-started#quota">quota</a>.', 'domain': 'youtube.quota', 'reason': 'quotaExceeded'}]">
"""

# TODO: add exception to capture quotaExceeded


class SettingsError(Exception):
    """Exeptions for wrong argumets in youtube resource function"""

class RequestError(Exception):
    """Common exception for request error(connect + status code)"""

