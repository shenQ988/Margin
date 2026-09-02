from nanobot.agent.tools.weread import (
    WeReadTool,
    WeReadToolConfig,
    build_author_recommendations,
    build_topic_advisor,
)


def test_weread_tool_description_prioritizes_catalog_for_book_discovery():
    description = WeReadTool(WeReadToolConfig()).description

    assert "before web search" in description
    assert "scope=10" in description
    assert "recommend_author" in description


def test_author_recommendations_validate_bilingual_owned_editions_before_the_llm_sees_candidates():
    result = build_author_recommendations(
        "Jane Austen",
        {
            "books": [
                {
                    "bookId": "owned-pride",
                    "title": "Pride and Prejudice",
                    "category": "Classics",
                    "finishReading": 0,
                    "readUpdateTime": 1,
                }
            ]
        },
        {
            "books": [
                {"bookId": "owned-pride", "reviewCount": 1, "noteCount": 5, "bookmarkCount": 0}
            ]
        },
        {
            "results": [
                {
                    "books": [
                        {"bookInfo": {"bookId": "edition-1", "title": "Pride and Prejudice", "author": "Jane Austen"}},
                        {"bookInfo": {"bookId": "edition-2", "title": "Pride and Prejudice", "author": "Jane Austen"}},
                        {
                            "bookInfo": {
                                "bookId": "translated-pride",
                                "title": "傲慢与偏见（英文原版）Pride and Prejudice",
                                "author": "Jane Austen",
                            }
                        },
                        {"bookInfo": {"bookId": "emma", "title": "Emma", "author": "Jane Austen"}},
                        {"bookInfo": {"bookId": "emma-alt", "title": "Emma (Illustrated)", "author": "Jane Austen"}},
                        {"bookInfo": {"bookId": "persuasion", "title": "Persuasion", "author": "Jane Austen"}},
                    ]
                }
            ]
        },
    )

    assert result["profile"]["deepReadTopics"] == ["Classics"]
    assert result["profile"]["activeBooks"] == ["Pride and Prejudice"]
    assert result["ownedBooks"] == [{"title": "Pride and Prejudice", "author": None}]
    assert [candidate["title"] for candidate in result["candidates"]] == [
        "Emma",
        "Persuasion",
    ]
    assert {
        "title": "傲慢与偏见（英文原版）Pride and Prejudice",
        "reason": "same_work_as_owned",
        "ownedTitle": "Pride and Prejudice",
    } in result["validation"]["rejectedCandidates"]
    assert "rejectedCandidates are forbidden" in result["rules"]["response"]


async def test_recommend_author_fetches_live_profile_and_ebook_catalog(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def fake_call(_api_key: str, api_name: str, **params):
        calls.append((api_name, params))
        return {"books": [], "results": []}

    monkeypatch.setattr("nanobot.agent.tools.weread.call_weread_api", fake_call)

    response = await WeReadTool(WeReadToolConfig(api_key="test-key")).execute(
        action="recommend_author", keyword="Jane Austen"
    )

    assert '"candidates": []' in response
    assert ("/shelf/sync", {}) in calls
    assert ("/user/notebooks", {"count": 200}) in calls
    assert ("/store/search", {"keyword": "Jane Austen", "scope": 10}) in calls


def test_topic_advisor_classifies_reading_evidence_and_sets_a_path_route():
    result = build_topic_advisor(
        "product management",
        {
            "books": [
                {"bookId": "one", "title": "Product Management", "category": "Product Management"},
                {"bookId": "two", "title": "Product Strategy", "category": "Product Management"},
                {"bookId": "three", "title": "Product Discovery", "category": "Product Management"},
                {"bookId": "dormant", "title": "Product Metrics", "category": "Product Management"},
            ]
        },
        {
            "books": [
                {"bookId": "one", "noteCount": 5},
                {"bookId": "two", "reviewCount": 6},
                {"bookId": "three", "bookmarkCount": 7},
                {"bookId": "hidden", "title": "Hidden Product Notes", "noteCount": 10},
            ]
        },
        {"results": [{"books": [{"bookInfo": {"bookId": "next", "title": "Inspired"}}]}]},
    )

    assert result["workflow"]["route"] == "advisor"
    assert [book["title"] for book in result["analysis"]["trueReads"]] == [
        "Product Discovery",
        "Product Strategy",
        "Product Management",
    ]
    assert result["analysis"]["dormant"] == [
        {"title": "Product Metrics", "notes": 0, "category": "Product Management"}
    ]
    assert result["analysis"]["hiddenDeepReads"] == [
        {"bookId": "hidden", "title": "Hidden Product Notes", "notes": 10}
    ]


async def test_advisor_fetches_live_shelf_notes_and_ebook_candidates(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def fake_call(_api_key: str, api_name: str, **params):
        calls.append((api_name, params))
        return {"books": [], "results": []}

    monkeypatch.setattr("nanobot.agent.tools.weread.call_weread_api", fake_call)

    response = await WeReadTool(WeReadToolConfig(api_key="test-key")).execute(
        action="advisor", keyword="product management"
    )

    assert '"route": "path"' in response
    assert ("/shelf/sync", {}) in calls
    assert ("/user/notebooks", {"count": 200}) in calls
    assert ("/store/search", {"keyword": "product management", "scope": 10}) in calls
