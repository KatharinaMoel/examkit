import json, pathlib, copy, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engine import validate as v

EX = pathlib.Path(__file__).resolve().parents[1] / "example"

def load():
    exam = json.loads((EX / "exam.json").read_text())
    cov = json.loads((EX / "coverage.json").read_text())
    cards = v.load_cards(EX / "cards")
    return exam, cov, cards

def run(cards, exam=None, cov=None):
    e, c, _ = load()
    return v.validate(cards, exam or e, cov or c, EX / "notes", EX / "sources")

def test_example_is_valid():
    _, _, cards = load()
    assert run(cards) == []

def test_detects_planted_error_first():
    # Lernprotokoll 13.09.: erst einen Treffer erzeugen, dann messen
    _, _, cards = load()
    bad = copy.deepcopy(cards); del bad[0]["a"]
    assert any("field a" in m for m in run(bad))

def test_unknown_guide_id():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[1]["src"] = "guide:3.9"
    msgs = run(bad)
    assert any("guide:3.9" in m for m in msgs)

def test_note_heading_renamed():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["src"] = "note:intro#What a basic was"
    msgs = run(bad)
    assert any("intro.md" in m and "What a basic was" in m for m in msgs)

def test_missing_source_file():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[2]["src"] = "source:nope.md"
    assert any("nope.md" in m for m in run(bad))

def test_bad_src_format():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["src"] = "01 §1 Schachtelung"
    assert any("src" in m and "01 §1" in m for m in run(bad))

def test_language_not_allowed():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["lang"] = "fr"
    assert any("lang" in m and "fr" in m for m in run(bad))

def test_covers_unknown_id():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["covers"] = ["9.9"]
    assert any("covers" in m and "9.9" in m for m in run(bad))

def test_duplicate_id():
    _, _, cards = load()
    bad = copy.deepcopy(cards) + [copy.deepcopy(cards[0])]
    assert any("duplicate" in m and "ex-basic-def" in m for m in run(bad))

def test_priority_and_deck_and_ctx_src():
    _, _, cards = load()
    bad = copy.deepcopy(cards)
    bad[0]["p"] = 4; bad[1]["deck"] = "nope"; bad[2]["ctx_src"] = "guess"
    msgs = run(bad)
    assert any("p must be" in m for m in msgs)
    assert any("deck" in m and "nope" in m for m in msgs)
    assert any("ctx_src" in m and "guess" in m for m in msgs)

def test_no_cards():
    assert any("no cards" in m for m in run([]))

def _with(**changes):
    _, _, cards = load()
    bad = copy.deepcopy(cards)
    bad[0].update(changes)
    return run(bad)

def test_covers_null_does_not_crash():
    assert any("covers must be a list of ids" in m for m in _with(covers=None))

def test_covers_nested_list_does_not_crash():
    assert any("covers must be a list of ids" in m for m in _with(covers=[["x"]]))

def test_covers_string_is_rejected():
    msgs = _with(covers="1.1")
    assert any("covers must be a list of ids" in m for m in msgs)
    assert len(msgs) == 1

def test_key_string_is_rejected():
    assert any("key must be a list of strings" in m for m in _with(key="smallest unit"))

def test_deck_list_does_not_crash():
    assert any("deck" in m for m in _with(deck=["a"]))

def test_ctx_src_and_lang_lists_do_not_crash():
    msgs = _with(ctx_src=["a"], lang=["en"])
    assert any("ctx_src" in m for m in msgs)
    assert any("lang" in m for m in msgs)

def test_id_list_does_not_crash():
    assert any("id must be a string" in m for m in _with(id=["a"]))

def test_bare_string_card(tmp_path):
    (tmp_path / "x.json").write_text('["x"]')
    cards = v.load_cards(tmp_path)
    msgs = run(cards)
    assert any("card #1 in x.json is not an object" in m for m in msgs)

def test_p_bool_and_float_rejected():
    assert any("p must be" in m for m in _with(p=True))
    assert any("p must be" in m for m in _with(p=1.0))

def test_messages_include_file():
    msgs = _with(p=4)
    assert any("ex-basic-def (basics.json)" in m for m in msgs)
