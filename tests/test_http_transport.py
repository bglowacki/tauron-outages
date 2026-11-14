from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tauron_outages.http_transport import BASE_URL, urllib_transport
from tauron_outages.outage_feed import OutageFeed, OutageFeedError

from conftest import ADDRESS

PARAMS = {
    "cityGAID": "111",
    "streetGAID": "222",
    "houseNo": "12 A",
    "fromDate": "2026-11-14T09:00:00.123Z",
    "_": "1794646800123",
}


@pytest.fixture
def server():
    state = {"status": 200, "body": b'{"OutageItems": []}', "delay": 0.0, "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["paths"].append(self.path)
            time.sleep(state["delay"])
            try:
                self.send_response(state["status"])
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(state["body"])
            except BrokenPipeError:
                pass

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{httpd.server_address[1]}/waapi/outages/address"
    yield state
    httpd.shutdown()
    httpd.server_close()


def call(server, timeout=5):
    return asyncio.run(urllib_transport(server["url"], timeout=timeout)(PARAMS))


def fetch_through_feed(url, timeout=5):
    feed = OutageFeed(ADDRESS, urllib_transport(url, timeout=timeout), timezone.utc)
    return asyncio.run(feed.fetch(datetime(2026, 11, 14, tzinfo=timezone.utc)))


def test_points_at_tauron_by_default():
    assert BASE_URL == "https://www.tauron-dystrybucja.pl/waapi/outages/address"


def test_returns_decoded_json_whatever_the_content_type(server):
    server["body"] = '{"OutageItems": [{"Message": "Łąka"}]}'.encode()

    assert call(server) == {"OutageItems": [{"Message": "Łąka"}]}


def test_sends_parameters_url_encoded_in_order(server):
    call(server)

    assert server["paths"] == [
        "/waapi/outages/address?cityGAID=111&streetGAID=222&houseNo=12+A"
        "&fromDate=2026-11-14T09%3A00%3A00.123Z&_=1794646800123"
    ]


@pytest.mark.parametrize("status", [404, 500, 503])
def test_http_error_status_is_a_feed_error(server, status):
    server["status"] = status

    with pytest.raises(OutageFeedError):
        fetch_through_feed(server["url"])


def test_invalid_json_is_a_feed_error(server):
    server["body"] = b"<html>maintenance</html>"

    with pytest.raises(OutageFeedError):
        fetch_through_feed(server["url"])


def test_timeout_is_a_feed_error(server):
    server["delay"] = 0.5

    with pytest.raises(OutageFeedError):
        fetch_through_feed(server["url"], timeout=0.1)


def test_connection_refused_is_a_feed_error():
    with pytest.raises(OutageFeedError):
        fetch_through_feed("http://127.0.0.1:9/nothing", timeout=1)
