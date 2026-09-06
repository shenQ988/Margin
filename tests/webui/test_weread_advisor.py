import json

from websockets.datastructures import Headers
from websockets.http11 import Request as WsRequest

from nanobot.webui import weread_api
from nanobot.webui.weread_api import build_reading_profile
from nanobot.webui.ws_http import GatewayHTTPHandler


def test_reading_profile_classifies_books_and_recommends_matching_dormant_book():
    profile = build_reading_profile(
        {
            "books": [
                {"bookId": "deep", "title": "Inspired", "author": "Marty Cagan", "category": "Product", "finishReading": 1},
                {"bookId": "active", "title": "The Mom Test", "author": "Rob Fitzpatrick", "category": "Product", "finishReading": 0, "readUpdateTime": 1_700_000_000},
                {"bookId": "next", "title": "Continuous Discovery Habits", "author": "Teresa Torres", "category": "Product", "finishReading": 0},
                {"bookId": "other", "title": "Design of Everyday Things", "author": "Don Norman", "category": "Design", "finishReading": 0},
            ]
        },
        {"books": [{"bookId": "deep", "reviewCount": 2, "noteCount": 2, "bookmarkCount": 2}]},
        now_timestamp=1_700_000_000,
    )

    assert [book["title"] for book in profile["deepReads"]] == ["Inspired"]
    assert [book["title"] for book in profile["activeBooks"]] == ["The Mom Test"]
    assert [book["title"] for book in profile["dormantBooks"]] == [
        "Continuous Discovery Habits",
        "Design of Everyday Things",
    ]
    assert profile["topics"] == [{"name": "Product", "deepReadCount": 1}]
    assert profile["recommendation"]["title"] == "Continuous Discovery Habits"
    assert "Product" in profile["recommendation"]["reason"]


def test_reading_profile_never_recommends_a_deep_read_or_invents_a_topic():
    profile = build_reading_profile(
        {"books": [{"bookId": "read", "title": "Read Book", "finishReading": 1}]},
        {"books": [{"bookId": "read", "reviewCount": 5}]},
        now_timestamp=1_700_000_000,
    )

    assert profile["recommendation"] is None
    assert profile["topics"] == []
    assert profile["confidence"] == "high"


async def test_topic_advisor_returns_weread_catalog_suggestions(monkeypatch):
    async def fake_call(_api_key, path, **_params):
        if path == "/shelf/sync":
            return {"books": [{"bookId": "owned", "title": "Inspired", "category": "Product"}]}
        if path == "/user/notebooks":
            return {"books": []}
        if path == "/store/search":
            return {
                "results": [
                    {
                        "books": [
                            {
                                "bookInfo": {
                                    "bookId": "catalog-1",
                                    "title": "The Mom Test",
                                    "author": "Rob Fitzpatrick",
                                    "category": "Business",
                                    "deepLink": "https://weread.qq.com/catalog-1",
                                }
                            }
                        ]
                    }
                ]
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(weread_api, "call_weread_api", fake_call)

    profile = await weread_api.fetch_advisor("product management")

    assert profile["topic"] == "product management"
    assert profile["suggestedBooks"] == [
        {
            "bookId": "catalog-1",
            "title": "The Mom Test",
            "author": "Rob Fitzpatrick",
            "category": "Business",
            "deepLink": "https://weread.qq.com/catalog-1",
            "step": 1,
            "level": "Beginner",
            "reason": "Start here to establish the core vocabulary and questions for this topic.",
            "topic": "product management",
        }
    ]


async def test_advisor_http_route_reads_topic_from_request_path(monkeypatch):
    received_topics: list[str | None] = []

    async def fake_fetch_advisor(topic: str | None):
        received_topics.append(topic)
        return {"topic": topic}

    handler = object.__new__(GatewayHTTPHandler)
    handler.check_api_token = lambda _request: True
    monkeypatch.setattr("nanobot.webui.ws_http.fetch_advisor", fake_fetch_advisor)

    response = await handler._handle_weread_advisor(
        WsRequest("/api/weread/advisor?topic=product%20management", Headers())
    )

    assert received_topics == ["product management"]
    assert json.loads(response.body) == {"topic": "product management"}
