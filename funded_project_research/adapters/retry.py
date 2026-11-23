"""Bounded, observable retries for source page requests."""
from __future__ import annotations

import ssl
import sys
import time
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError

from ..status import utc_now
from .base import SourceError

TRANSIENT_HTTP = {408, 500, 502, 503, 504}
REQUEST_ERRORS = (URLError, ConnectionError, TimeoutError, IncompleteRead, ssl.SSLError, SourceError)
CONSECUTIVE_FAILURE_LIMIT = 3


class RequestTimeLimit(SourceError):
    def __init__(self):
        super().__init__("request_time_limit")


def request_error_kind(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"http_{error.code}"
    if isinstance(error, ssl.SSLError):
        return "tls"
    if isinstance(error, URLError):
        if isinstance(error.reason, ssl.SSLError):
            return "tls"
        if isinstance(error.reason, TimeoutError):
            return "timeout"
        return "network"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (ConnectionError, IncompleteRead)):
        return "network"
    return str(error)


def transient(error: Exception) -> bool:
    if isinstance(error, HTTPError):
        return error.code in TRANSIENT_HTTP
    if isinstance(error, URLError):
        return not isinstance(error.reason, ssl.SSLError)
    return isinstance(error, (ConnectionError, TimeoutError, IncompleteRead))


class SourceRequests:
    REQUEST_TIMEOUT = 30
    SOURCE_SECONDS = 240
    MAX_RETRIES = 8
    RETRY_DELAY = 1

    def __init__(self, source: str, *, seconds: int | None = None):
        self.source = source
        self.deadline = time.monotonic() + (self.SOURCE_SECONDS if seconds is None else seconds)
        self.retries_left = self.MAX_RETRIES

    def recover(self, stage, target, fetch, *args):
        if self.retries_left <= 0:
            raise SourceError("retry_limit")
        self.retries_left -= 1
        time.sleep(self.RETRY_DELAY)
        return self.fetch(stage, target, fetch, *args)

    def fetch(self, stage, target, fetch, *args):
        for attempt in (1, 2):
            attempted = utc_now()
            context = f"[source-request] {self.source} {stage} {target} at={attempted} attempt={attempt}"
            try:
                left = self.deadline - time.monotonic()
                if left <= 0:
                    raise RequestTimeLimit()
                data = fetch(*args, timeout=min(self.REQUEST_TIMEOUT, left))
            except REQUEST_ERRORS as error:
                if isinstance(error, HTTPError):
                    error.close()
                retry = (attempt == 1 and self.retries_left > 0 and transient(error)
                         and self.deadline - time.monotonic() > self.RETRY_DELAY)
                outcome = "retry_scheduled" if retry else "request_failed"
                print(f"{context} {outcome} kind={request_error_kind(error)}", file=sys.stderr)
                if not retry:
                    raise
                self.retries_left -= 1
                time.sleep(self.RETRY_DELAY)
            else:
                if attempt > 1:
                    print(f"{context} recovered", file=sys.stderr)
                return data
