"""The intent step parses the LLM's JSON and always yields a usable (title, question)."""

from zulip_researcher import intent


def test_derive_parses_title_and_question():
    raw = '{"title": "Ingest: Foo", "question": "What is Foo?"}'
    title, question = intent.derive("https://x/foo", ask=lambda task: raw)
    assert title == "Ingest: Foo"
    assert question == "What is Foo?"


def test_derive_extracts_json_from_surrounding_prose():
    raw = 'Sure!\n```json\n{"title": "T", "question": "Q?"}\n```'
    assert intent.derive("m", ask=lambda task: raw) == ("T", "Q?")


def test_derive_falls_back_to_the_message_on_garbage():
    title, question = intent.derive("Just this text", ask=lambda task: "not json")
    assert title == "Just this text"
    assert question == "Just this text"


def test_derive_survives_an_ask_failure():
    def boom(task):
        raise RuntimeError("omp down")

    assert intent.derive("fallback text", ask=boom) == ("fallback text", "fallback text")


def test_derive_truncates_to_limits():
    raw = '{"title": "%s", "question": "%s"}' % ("t" * 100, "x" * 500)
    title, question = intent.derive("m", ask=lambda task: raw)
    assert len(title) <= intent.TITLE_MAX
    assert len(question) <= intent.QUESTION_MAX
