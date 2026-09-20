"""The intent step parses the LLM's JSON and always yields a usable thread title."""

from zulip_researcher import intent


def test_derive_parses_title():
    raw = '{"title": "Ingest: Foo"}'
    assert intent.derive("https://x/foo", ask=lambda task: raw) == "Ingest: Foo"


def test_derive_extracts_json_from_surrounding_prose():
    raw = 'Sure!\n```json\n{"title": "T"}\n```'
    assert intent.derive("m", ask=lambda task: raw) == "T"


def test_derive_falls_back_to_the_message_on_garbage():
    assert intent.derive("Just this text", ask=lambda task: "not json") == "Just this text"


def test_derive_survives_an_ask_failure():
    def boom(task):
        raise RuntimeError("omp down")

    assert intent.derive("fallback text", ask=boom) == "fallback text"


def test_derive_truncates_to_limit():
    raw = '{"title": "%s"}' % ("t" * 100)
    assert len(intent.derive("m", ask=lambda task: raw)) <= intent.TITLE_MAX
