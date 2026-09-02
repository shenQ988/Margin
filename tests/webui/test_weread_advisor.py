from nanobot.webui.weread_api import build_reading_profile


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
