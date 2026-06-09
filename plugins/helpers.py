# VERSION: 1.55

# Author:
#  Christophe DUMEZ (chris@qbittorrent.org)

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of the author nor the names of its contributors may be
#      used to endorse or promote products derived from this software without
#      specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import datetime
import gzip
import html
import io
import os
import socket
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any, Optional, cast

import socks


def _getBrowserUserAgent() -> str:
    """Disguise as browser to circumvent website blocking"""

    # Firefox release calendar
    # https://whattrainisitnow.com/calendar/
    # https://wiki.mozilla.org/index.php?title=Release_Management/Calendar&redirect=no

    baseDate = datetime.date(2024, 4, 16)
    baseVersion = 125

    nowDate = datetime.date.today()
    nowVersion = baseVersion + ((nowDate - baseDate).days // 30)

    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{nowVersion}.0) Gecko/20100101 Firefox/{nowVersion}.0"


_headers: dict[str, str] = {"User-Agent": _getBrowserUserAgent()}
_original_socket = socket.socket


def enable_socks_proxy(enable: bool) -> None:
    if enable:
        socksURL = os.environ.get("qbt_socks_proxy")
        if socksURL is not None:
            parts = urllib.parse.urlsplit(socksURL)
            resolveHostname = (parts.scheme == "socks4a") or (parts.scheme == "socks5h")
            if (parts.scheme == "socks4") or (parts.scheme == "socks4a"):
                socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS4, parts.hostname, parts.port, resolveHostname)
                socket.socket = cast(type[socket.socket], socks.socksocket)  # type: ignore[misc]
            elif (parts.scheme == "socks5") or (parts.scheme == "socks5h"):
                socks.setdefaultproxy(
                    socks.PROXY_TYPE_SOCKS5,
                    parts.hostname,
                    parts.port,
                    resolveHostname,
                    parts.username,
                    parts.password,
                )
                socket.socket = cast(type[socket.socket], socks.socksocket)  # type: ignore[misc]
    else:
        socket.socket = _original_socket  # type: ignore[misc]


# This is only provided for backward compatibility, new code should not use it
htmlentitydecode = html.unescape


def retrieve_url(
    url: str,
    custom_headers: Mapping[str, str] = {},
    request_data: Optional[Any] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
    unescape_html_entities: bool = True,
) -> str:
    """Return the content of the url page as a string"""

    request = urllib.request.Request(url, request_data, {**_headers, **custom_headers})
    try:
        response = urllib.request.urlopen(request, context=ssl_context, timeout=30)
    except urllib.error.URLError as errno:
        print(f"Connection error: {errno.reason}", file=sys.stderr)
        return ""
    data: bytes = response.read()

    # Check if it is gzipped
    if data[:2] == b"\x1f\x8b":
        # Data is gzip encoded, decode it
        with (
            io.BytesIO(data) as compressedStream,
            gzip.GzipFile(fileobj=compressedStream) as gzipper,
        ):
            data = gzipper.read()

    charset = "utf-8"
    try:
        charset = response.getheader("Content-Type", "").split("charset=", 1)[1]
    except IndexError:
        pass

    dataStr = data.decode(charset, "replace")

    if unescape_html_entities:
        dataStr = html.unescape(dataStr)

    return dataStr


def download_file(
    url: str,
    referer: Optional[str] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
) -> str:
    """Download file at url and write it to a file, return the path to the file and the url"""

    # Download url
    request = urllib.request.Request(url, headers=_headers)
    if referer is not None:
        request.add_header("referer", referer)
    response = urllib.request.urlopen(request, context=ssl_context, timeout=30)
    data = response.read()

    # Check if it is gzipped
    if data[:2] == b"\x1f\x8b":
        # Data is gzip encoded, decode it
        with (
            io.BytesIO(data) as compressedStream,
            gzip.GzipFile(fileobj=compressedStream) as gzipper,
        ):
            data = gzipper.read()

    # Write it to a file
    fileHandle, path = tempfile.mkstemp()
    with os.fdopen(fileHandle, "wb") as file:
        file.write(data)

    # return file path
    return f"{path} {url}"


DEFAULT_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://public.popcorn-tracker.org:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce",
    "udp://p4p.arenabg.ch:1337/announce",
]


def build_magnet_link(info_hash: str, name: str, trackers: Optional[list] = None) -> str:
    """Build a magnet link from info hash and name.

    Args:
        info_hash: The torrent info hash (40 character hex string)
        name: The torrent name
        trackers: Optional list of tracker URLs. Uses DEFAULT_TRACKERS if None.

    Returns:
        A properly formatted magnet URI string
    """
    if trackers is None:
        trackers = DEFAULT_TRACKERS

    encoded_name = urllib.parse.quote(name)
    trackers_str = "&".join([f"tr={urllib.parse.quote(t)}" for t in trackers])
    return f"magnet:?xt=urn:btih:{info_hash}&dn={encoded_name}&{trackers_str}"


def fetch_magnet_from_page(url: str, regex_pattern: Optional[str] = None) -> str:
    """Fetch magnet link from a web page.

    Args:
        url: The URL of the page to fetch
        regex_pattern: Optional custom regex pattern. Uses default if None.

    Returns:
        The magnet link if found, empty string otherwise
    """
    import re

    if regex_pattern is None:
        regex_pattern = r'magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^\s"<>\']*'

    try:
        page_content = retrieve_url(url)
        match = re.search(regex_pattern, page_content)
        if match:
            return match.group(0)
    except Exception:
        pass

    return ""
