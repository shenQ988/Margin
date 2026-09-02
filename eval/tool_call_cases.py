"""Labeled dataset of tool-calling test cases for the reading agent.

Each case asks: given this question (optionally with prior turns in the
same session), which single tool call — if any — should the agent make in
response? This measures *tool selection*, not final-answer quality; a case
passes if the right tool (and, when specified, the right argument subset)
gets invoked, regardless of what the agent eventually says.

Tool names use underscores (``weread_shelf``, not ``weread.shelf``):
OpenAI/Anthropic function-calling APIs restrict tool names to
``[a-zA-Z0-9_-]``, so a literal dotted name would be rejected outright by
a real provider call — and this harness exists specifically to exercise
real provider calls (see eval/run_eval.py), not mocked ones.

``session_setup`` and ``expected_tools`` (see ``ToolCallCase``) are
dataset-only fields as of the "parametric confidence / session reuse /
context contamination / compound question / false positive / implicit
recency" case groups below: eval/trace_capture.py and eval/run_eval.py
don't execute session_setup turns or score against expected_tools yet.
Those cases are recorded now, correctly labeled, so the harness's actual
runtime behavior against them can be wired up as a separate change without
re-litigating what each case is supposed to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Category constants for the newer, more specifically-named case groups
# below (session-reuse / contamination / compound / false-positive /
# recency). Older cases still use bare string literals ("positive",
# "negative", "regression", "ambiguous") for their category field — both
# forms are just strings, so they compare equal fine; these constants
# exist for the newer, more numerous case groups where a typo'd literal
# would be easy to miss.
CATEGORY_PARAMETRIC_CONFIDENCE = "parametric_confidence_override"
CATEGORY_SESSION_REUSE = "same_session_reuse"
CATEGORY_CONTEXT_CONTAMINATION = "context_contamination"
CATEGORY_COMPOUND_QUESTION = "compound_multi_tool"
CATEGORY_FALSE_POSITIVE = "false_positive_trigger"
CATEGORY_IMPLICIT_RECENCY = "implicit_recency"


@dataclass
class ToolCallCase:
    id: str
    question: str
    expected_tool: str | None  # None means NO tool call should happen
    expected_args: dict[str, Any] | None = None  # partial match: only given keys checked
    # For cases needing more than one call to be fully correct (e.g. "check
    # the shelf, then check progress"). ``expected_tool`` above must equal
    # ``expected_tool_sequence[0]`` when both are set — it's still what
    # drives the hard pass/fail invocation_correct/recall/precision metrics.
    # A short/partial sequence (e.g. stopping after step 1 when that alone
    # answers the question) is scored separately as a softer
    # ``sequence_accuracy`` signal — see eval/scorer.py — rather than
    # failing the case outright, since a single well-justified call can be
    # legitimately sufficient even when a longer sequence would also work.
    expected_tool_sequence: list[str] | None = None
    notes: str = ""
    category: str = "positive"  # "positive" | "negative" | "regression" | "ambiguous" | one of the CATEGORY_* constants above
    # Cases sharing a session_group run in EVAL_CASES list order inside the
    # SAME session, so later cases see earlier turns' history — this is what
    # lets a regression case assert "the tool gets called again even though
    # this was already asked and answered." Cases with session_group=None
    # each get their own fresh, isolated session.
    session_group: str | None = None
    # Prior user turns to run, in order, in the same session BEFORE the
    # actual test ``question`` — a self-contained alternative to
    # session_group for cases that only need one case object instead of a
    # paired group (e.g. "mention X, then ask Y and confirm X wasn't
    # trusted as fact"). NOTE: as of this addition, eval/trace_capture.py
    # and eval/run_eval.py do not yet execute session_setup turns — this
    # field is dataset-only scaffolding until the harness is wired up to
    # consume it (out of scope for this change; see module docstring below
    # for the cases that rely on it).
    session_setup: list[str] = field(default_factory=list)
    # For cases needing multiple tool calls to be fully correct, checked
    # instead of expected_tool. Like session_setup above, this is
    # currently dataset-only: eval/scorer.py does not yet score against
    # expected_tools (only expected_tool / expected_tool_sequence). When
    # set, expected_tool should still be populated with the first expected
    # call, consistent with the expected_tool_sequence convention, so
    # existing scoring still evaluates that first call correctly in the
    # meantime.
    expected_tools: list[str] | None = None
    # Deterministic checks for the final response. They are deliberately
    # narrow and case-specific: use them when an exact response-quality
    # regression (such as duplicate book recommendations) is known.
    required_answer_terms: list[str] = field(default_factory=list)
    max_answer_term_occurrences: dict[str, int] = field(default_factory=dict)


EVAL_CASES: list[ToolCallCase] = [
    # ---- Positive cases: one per registered tool ---------------------------
    ToolCallCase(
        id="topic_advisor_plan",
        question=(
            "I want to go deeper into product management. Recommend three books available in WeRead, "
            "tailored to what I have already studied."
        ),
        expected_tool="weread_topic_advisor",
        expected_args={"keyword": "product management"},
        required_answer_terms=["Inspired", "Empowered", "Lean Analytics", "best next"],
        notes=(
            "A topic-specific request with explicit count and source constraints must use the advisor, "
            "not a generic recommendation or web search. The final response must rely on distinct verified candidates."
        ),
    ),
    ToolCallCase(
        id="catalog_author_discovery",
        question="I already own Pride and Prejudice. Recommend more books by Jane Austen.",
        expected_tool="weread_author_recommendations",
        expected_args={"keyword": "Jane Austen"},
        required_answer_terms=["Emma", "Persuasion", "Sense and Sensibility", "classic"],
        max_answer_term_occurrences={"Pride and Prejudice": 1},
        notes=(
            "Book discovery must prefer the WeRead ebook catalog over generic web search, "
            "then recommend distinct alternatives instead of repeating the user's existing book."
        ),
    ),
    ToolCallCase(
        id="bookshelf_basic",
        question="what's on my bookshelf?",
        expected_tool="weread_shelf",
    ),
    ToolCallCase(
        id="progress_specific",
        question="how far am I into Pride and Prejudice?",
        expected_tool="weread_progress",
        expected_args={"book_title": "Pride and Prejudice"},
    ),
    ToolCallCase(
        id="notebooks_overview",
        question="which of my books have notes or highlights on them?",
        expected_tool="weread_notebooks",
    ),
    ToolCallCase(
        id="bookmarklist_direct",
        question="show me the actual highlighted passages from Sapiens",
        expected_tool="weread_bookmarklist",
        expected_args={"book_title": "Sapiens"},
    ),
    ToolCallCase(
        id="stats_weekly",
        question="how many hours have I spent reading this week?",
        expected_tool="weread_stats",
    ),
    ToolCallCase(
        id="ask_about_book_case",
        question="In Sapiens, what does Harari argue is unique about human cooperation?",
        expected_tool="ask_about_book",
        expected_args={"book_title": "Sapiens"},
    ),
    ToolCallCase(
        id="digest_request",
        question="give me my weekly reading digest",
        expected_tool="generate_weekly_digest",
    ),
    ToolCallCase(
        id="profile_check",
        question="what are my top reading topics lately?",
        expected_tool="get_reading_profile",
    ),
    ToolCallCase(
        id="add_item_case",
        question="add Project Hail Mary by Andy Weir to my reading list",
        expected_tool="add_reading_item",
        expected_args={"title": "Project Hail Mary"},
    ),
    # ---- Negative cases: no tool call should happen -------------------------
    ToolCallCase(
        id="general_knowledge",
        question="who wrote Pride and Prejudice?",
        expected_tool=None,
        category="negative",
        notes="general knowledge, no live/personal data needed, model should just answer",
    ),
    ToolCallCase(
        id="opinion_question",
        question="do you think reading fiction is valuable?",
        expected_tool=None,
        category="negative",
    ),
    ToolCallCase(
        id="chitchat_thanks",
        question="thanks, that's really helpful!",
        expected_tool=None,
        category="negative",
    ),
    ToolCallCase(
        id="meta_capabilities",
        question="what kinds of things can you help me with?",
        expected_tool=None,
        category="negative",
        notes="asks about the agent itself, not the user's reading data",
    ),
    # ---- Regression cases: stale-memory / premature-answer bugs -------------
    # Pattern: ask the same kind of question twice in one session. The
    # second ask must STILL trigger a fresh tool call — this is a direct
    # regression test for the bug fixed in nanobot/agent/memory_classification.py,
    # where a WeRead tool result answered once could get folded into
    # session-summary/long-term memory and resurface as a stale answer on
    # a later ask instead of a fresh tool call.
    ToolCallCase(
        id="repeat_shelf_q1",
        question="what's on my bookshelf?",
        expected_tool="weread_shelf",
        category="regression",
        session_group="regression_repeat_shelf",
        notes="first ask — establishes history for repeat_shelf_q2",
    ),
    ToolCallCase(
        id="repeat_shelf_q2",
        question="what's on my bookshelf again?",
        expected_tool="weread_shelf",
        category="regression",
        session_group="regression_repeat_shelf",
        notes=(
            "regression test for the stale-memory bug: must re-invoke "
            "weread_shelf even though this was already asked and answered "
            "earlier in this same session"
        ),
    ),
    ToolCallCase(
        id="repeat_notebooks_q1",
        question="which of my books have notes on them?",
        expected_tool="weread_notebooks",
        category="regression",
        session_group="regression_repeat_notebooks",
        notes="first ask — establishes history for repeat_notebooks_q2",
    ),
    ToolCallCase(
        id="repeat_notebooks_q2",
        question="remind me again which books have notes on them?",
        expected_tool="weread_notebooks",
        category="regression",
        session_group="regression_repeat_notebooks",
        notes=(
            "regression test for the stale-memory bug, same pattern as "
            "repeat_shelf_q2 but for weread_notebooks — must not be "
            "answered from the visible prior turn instead of a fresh call"
        ),
    ),
    ToolCallCase(
        id="tempting_general_activity",
        question="anything interesting going on with my reading lately?",
        expected_tool="generate_weekly_digest",
        category="regression",
        notes=(
            "phrased like small talk / an opinion question (which would "
            "correctly get expected_tool=None), but is actually a request "
            "for the user's own personalized reading activity — the model "
            "should not default to a generic conversational non-tool reply"
        ),
    ),
    # ---- Ambiguous cases: genuinely tricky tool-selection judgment calls ----
    # Unlike the regression cases above (which target a known, previously
    # observed bug), these probe boundaries the harness has never confirmed
    # broken — near-duplicate questions that should route to DIFFERENT
    # tools depending on subtle wording, questions that resemble a
    # personal-data request but aren't served by any registered tool, and
    # requests that sound actionable but aren't explicit enough to act on.
    ToolCallCase(
        id="vague_reading_status",
        question="how am I doing with my books this month?",
        expected_tool="generate_weekly_digest",
        category="ambiguous",
        notes=(
            "vague personalized-summary request; could plausibly be pulled "
            "toward weread_stats (time only) or get_reading_profile (topics "
            "only) instead, since none of the three tool descriptions "
            "obviously wins — digest is the intended catch-all for "
            "open-ended 'how am I doing' questions"
        ),
    ),
    ToolCallCase(
        id="ambiguous_recall_vs_content",
        question="remind me what Sapiens says about myths",
        expected_tool="ask_about_book",
        expected_args={"book_title": "Sapiens"},
        category="ambiguous",
        notes=(
            "'remind me' could tempt the model toward weread_bookmarklist "
            "(the user's own saved highlights) instead — but the question "
            "asks what the BOOK says, not what the user personally "
            "highlighted, so ask_about_book is correct. Paired with "
            "ambiguous_highlights_vs_content to test the model can "
            "distinguish both directions of this same ambiguity, not just "
            "default to one tool whenever 'myths'/'Sapiens' appear"
        ),
    ),
    ToolCallCase(
        id="ambiguous_highlights_vs_content",
        question="what were my highlighted notes about myths in Sapiens?",
        expected_tool="weread_bookmarklist",
        expected_args={"book_title": "Sapiens"},
        category="ambiguous",
        notes="mirror of ambiguous_recall_vs_content — 'my highlighted notes' "
        "explicitly asks for the user's own saved highlights, not the book's "
        "content in general, so this should route to weread_bookmarklist "
        "instead of ask_about_book",
    ),
    ToolCallCase(
        id="unsupported_metadata_question",
        question="how many pages does Sapiens have?",
        expected_tool=None,
        category="ambiguous",
        notes=(
            "no registered tool provides book metadata like page count — "
            "tests whether the model force-fits this into an available "
            "tool (most likely ask_about_book) rather than recognizing "
            "none of them actually serve this and just answering directly "
            "or saying it doesn't know"
        ),
    ),
    ToolCallCase(
        id="musing_not_a_request",
        question="I really want to read Educated by Tara Westover at some point",
        expected_tool=None,
        category="ambiguous",
        notes=(
            "expresses a wish, not an explicit request to add the book — "
            "add_reading_item should only fire on clear actionable intent "
            "('add this', 'put this on my list'), not passing musing; "
            "tests against over-eager tool calling, the mirror-image "
            "failure mode from add_item_case"
        ),
    ),
    ToolCallCase(
        id="vague_progress_reference",
        question="did I ever finish War and Peace?",
        expected_tool="weread_shelf",
        expected_tool_sequence=["weread_shelf", "weread_progress"],
        category="ambiguous",
        notes=(
            "a two-step lookup: check the shelf for War and Peace's status "
            "(finished/reading/to-read) first, then weread_progress for "
            "detail/confirmation. Phrased as a casual yes/no recollection "
            "question, which could tempt a conversational guess or an 'I "
            "don't have that information' non-tool reply instead — "
            "finished status is live data and must be fetched fresh "
            "regardless of how casually it's asked. A single weread_shelf "
            "call whose status field alone answers the question is a "
            "legitimate stop, not a failure — see expected_tool_sequence "
            "and sequence_accuracy in eval/scorer.py"
        ),
    ),
    ToolCallCase(
        id="shelf_vs_progress_ambiguous",
        question="am I still in the middle of Sapiens?",
        expected_tool="weread_shelf",
        category="ambiguous",
        notes=(
            "genuinely debatable: weread_progress (returns a percent) "
            "would also be a defensible call here. Labeled weread_shelf "
            "because the question asks about READING STATUS ('still in "
            "the middle of', i.e. reading vs finished vs to-read) rather "
            "than how FAR along the user is — but treat a weread_progress "
            "call on this case as a soft miss worth reviewing by hand, not "
            "an obvious bug, if it comes up in results"
        ),
    ),
    # ---- Parametric confidence override: famous books tempt the model to
    # answer from training data instead of grounding via ask_about_book.
    # Same underlying failure mode as ask_about_book_case above (see the
    # session where that was diagnosed), grouped here under an explicit
    # category name with more famous-book examples for broader coverage.
    ToolCallCase(
        id="parametric_sapiens_cooperation",
        question="what does Harari argue about cooperation in Sapiens?",
        expected_tool="ask_about_book",
        category=CATEGORY_PARAMETRIC_CONFIDENCE,
        notes=(
            "Sapiens is famous enough that the model can confidently "
            "free-recall this without grounding — that confidence is "
            "exactly the failure mode: a free-recalled answer sounds "
            "plausible but isn't grounded in the user's actual "
            "book/edition/highlighted context"
        ),
    ),
    ToolCallCase(
        id="parametric_pride_prejudice_opening",
        question="how does Pride and Prejudice open?",
        expected_tool="ask_about_book",
        category=CATEGORY_PARAMETRIC_CONFIDENCE,
        notes=(
            "the opening line ('It is a truth universally acknowledged...') "
            "is extremely well-known text the model has almost certainly "
            "memorized verbatim, making it maximally tempting to skip "
            "ask_about_book entirely"
        ),
    ),
    ToolCallCase(
        id="parametric_gatsby_green_light",
        question="what's the significance of the green light in Gatsby?",
        expected_tool="ask_about_book",
        category=CATEGORY_PARAMETRIC_CONFIDENCE,
        notes=(
            "a canonical, frequently-taught literary-analysis question — "
            "the model likely has a ready-made high-confidence answer from "
            "training, which is precisely why grounding via ask_about_book "
            "still matters here rather than less-famous books"
        ),
    ),
    # ---- Same-session reuse: regression-style tests for the stale-answer
    # bug, expressed via session_setup (prior turns bundled into one case)
    # rather than the session_group pairing used by the "regression" cases
    # above. session_setup is not yet executed by the harness runtime — see
    # the module docstring — so these currently only document intent.
    ToolCallCase(
        id="same_session_repeat_shelf_identical",
        session_setup=["what's on my bookshelf?"],
        question="what's on my bookshelf?",
        expected_tool="weread_shelf",
        category=CATEGORY_SESSION_REUSE,
        notes=(
            "the exact same question asked twice in one session — the "
            "second call must still hit weread_shelf fresh rather than "
            "reusing the first turn's already-visible answer"
        ),
    ),
    ToolCallCase(
        id="same_session_reuse_shelf_then_reading_filter",
        session_setup=["what's on my bookshelf?"],
        question="and what have I marked as currently reading?",
        expected_tool="weread_shelf",
        category=CATEGORY_SESSION_REUSE,
        notes=(
            "a narrower follow-up referencing the same underlying shelf "
            "data already stated in the prior turn — the model could "
            "plausibly just filter the earlier answer down to 'reading' "
            "status instead of re-fetching, but shelf state can change "
            "between turns so a fresh call is still required"
        ),
    ),
    ToolCallCase(
        id="same_session_reuse_progress_after_distance",
        session_setup=[
            "how far am I into Dune?",
            "tell me about the Fremen",
            "what other books has the author of Dune written?",
        ],
        question="how far am I into that book again?",
        expected_tool="weread_progress",
        expected_args={"book_title": "Dune"},
        category=CATEGORY_SESSION_REUSE,
        notes=(
            "three unrelated turns sit between the original progress "
            "answer and this repeat ask — tests whether conversational "
            "distance makes staleness more likely to slip through than "
            "an immediate back-to-back repeat would. 'that book' also "
            "requires resolving an anaphoric reference back to Dune "
            "across those intervening turns before the tool call can even "
            "be attempted correctly"
        ),
    ),
    # ---- Context contamination: user-stated claims in conversation must
    # not substitute for a fresh tool call, even when they sound like they
    # already answer the question.
    ToolCallCase(
        id="context_contamination_user_claimed_added",
        session_setup=["I just added Dune to my shelf"],
        question="what's on my shelf?",
        expected_tool="weread_shelf",
        category=CATEGORY_CONTEXT_CONTAMINATION,
        notes=(
            "the user's own claim that they added a book must not be "
            "trusted as fact — the client-side action could have failed, "
            "be delayed, or the user could be mistaken; only a fresh "
            "weread_shelf fetch confirms the actual current shelf state"
        ),
    ),
    ToolCallCase(
        id="context_contamination_incidental_stat_mention",
        session_setup=["I read somewhere that Atomic Habits sold 20 million copies"],
        question="what books do I have?",
        expected_tool="weread_shelf",
        category=CATEGORY_CONTEXT_CONTAMINATION,
        notes=(
            "an incidental trivia mention of a book title in conversation "
            "(not even a claim about the user's own shelf) must not get "
            "conflated with bookshelf data or cause the model to skip the "
            "fetch — tests contamination from merely mentioning a book "
            "title, not just from explicit claims like the case above"
        ),
    ),
    # ---- Compound questions needing multiple tool calls. expected_tools
    # records the full expected set; expected_tool is still set to the
    # first expected call so today's scorer (which only judges the first
    # call) evaluates these cases meaningfully in the meantime — see the
    # module docstring for why expected_tools itself isn't scored yet.
    ToolCallCase(
        id="compound_digest_and_recommendation",
        question=(
            "what have I read this week, and what should I read next "
            "based on my highlights?"
        ),
        expected_tool="generate_weekly_digest",
        expected_tools=["generate_weekly_digest", "get_reading_profile"],
        category=CATEGORY_COMPOUND_QUESTION,
        notes=(
            "bundles two distinct asks — a weekly activity summary and a "
            "personalized recommendation grounded in reading "
            "preferences/highlights — that plausibly require two separate "
            "tool calls; get_reading_profile is the closest registered "
            "tool for the recommendation half, since there's no dedicated "
            "recommendation tool in this registry"
        ),
    ),
    ToolCallCase(
        id="compound_progress_and_highlights",
        question="how far am I into Dune and what have I highlighted so far?",
        expected_tool="weread_progress",
        expected_args={"book_title": "Dune"},
        expected_tools=["weread_progress", "weread_notebooks"],
        category=CATEGORY_COMPOUND_QUESTION,
        notes=(
            "bundles two asks about the same book (percent progress, plus "
            "highlight content) that require two different tool calls. "
            "weread_notebooks is the cross-book notes overview rather than "
            "the single-book highlight text (that's weread_bookmarklist) — "
            "kept as weread_notebooks here to match the originally "
            "specified mapping, but weread_bookmarklist is arguably the "
            "more precise tool for 'what have I highlighted' about ONE "
            "named book; worth revisiting once expected_tools is actually "
            "scored"
        ),
    ),
    # ---- False-positive triggers: sound like they need a tool, genuinely
    # don't. Tests precision (not over-calling), the mirror image of the
    # negative cases near the top of this file, but phrased to specifically
    # resemble a personal-data or book-lookup request.
    ToolCallCase(
        id="false_positive_sapiens_genre",
        question="what genre is Sapiens?",
        expected_tool=None,
        category=CATEGORY_FALSE_POSITIVE,
        notes=(
            "sounds like it might need a book lookup, but genre "
            "classification is generic public knowledge, not personal or "
            "live data — tests against over-calling ask_about_book for "
            "a question it doesn't actually need to answer"
        ),
    ),
    ToolCallCase(
        id="false_positive_similar_author",
        question="who's a good author similar to Agatha Christie?",
        expected_tool=None,
        category=CATEGORY_FALSE_POSITIVE,
        notes=(
            "recommendation-flavored phrasing could tempt a call to "
            "get_reading_profile, but this isn't grounded in the user's "
            "own shelf/reading history at all — it's a generic public "
            "literary-recommendation question with no personal-data tool "
            "that applies"
        ),
    ),
    ToolCallCase(
        id="false_positive_book_length",
        question="is Pride and Prejudice a long book?",
        expected_tool=None,
        category=CATEGORY_FALSE_POSITIVE,
        notes=(
            "general public book-length trivia, not personal reading "
            "data — same underlying gap as unsupported_metadata_question "
            "(no tool serves book metadata), but framed as a yes/no "
            "question, which may read as more 'answerable via a tool' "
            "than an open factual question does"
        ),
    ),
    # ---- Implicit recency: hardest category. No explicit "now"/"current"
    # keyword flags the staleness risk — the tense/phrasing alone has to
    # be enough to recognize live data is needed.
    ToolCallCase(
        id="implicit_recency_what_am_i_reading",
        question="what am I reading?",
        expected_tool="weread_shelf",
        category=CATEGORY_IMPLICIT_RECENCY,
        notes=(
            "present tense implies current/live state with no explicit "
            "'now' or 'currently' keyword — tests whether the model "
            "recognizes an implicit recency requirement from tense alone, "
            "not just from explicit staleness-flagging language"
        ),
    ),
    ToolCallCase(
        id="implicit_recency_what_have_i_read",
        question="what have I read?",
        expected_tool="weread_shelf",
        category=CATEGORY_IMPLICIT_RECENCY,
        notes=(
            "paired with implicit_recency_what_am_i_reading to see if "
            "verb tense alone changes tool-invocation behavior. Reasoning "
            "for keeping the same expected tool despite the tense "
            "difference: 'what have I read' (present perfect, finished "
            "books) and 'what am I reading' (present, in-progress books) "
            "both resolve to shelf status filtered differently — this "
            "registry has no separate 'reading history' tool, so both "
            "still route through weread_shelf. The pair is still useful: "
            "it tests whether past-tense phrasing tempts the model to "
            "treat 'what have I read' as a static, already-settled fact "
            "(safe to answer from earlier context) rather than as live "
            "data that can change (e.g. a book finished five minutes ago)"
        ),
    ),
    ToolCallCase(
        id="implicit_recency_shelf_freshness_check",
        question="is my bookshelf up to date?",
        expected_tool="weread_shelf",
        category=CATEGORY_IMPLICIT_RECENCY,
        notes=(
            "no tool is named for 'check freshness' — weread_shelf is the "
            "closest available action, since answering meaningfully "
            "requires a fresh fetch to compare against whatever the model "
            "or user currently believes the shelf contains. Tests whether "
            "the model recognizes an implicit fetch requirement even when "
            "the question doesn't map cleanly onto any tool's literal "
            "description"
        ),
    ),
]
