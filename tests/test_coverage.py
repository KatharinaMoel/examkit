import copy, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engine import coverage as cov, validate as v

EX = pathlib.Path(__file__).resolve().parents[1] / "example"


def load():
    coverage = json.loads((EX / "coverage.json").read_text(encoding="utf-8"))
    cards = v.load_cards(EX / "cards")
    return coverage, cards


def test_detects_planted_error_first(tmp_path):
    (tmp_path / "x.md").write_text("---\ncovers: [9.9]\n---\n# x\n", encoding="utf-8")
    coverage, cards = load()
    _, errors = cov.compute(coverage, cards, tmp_path)
    assert errors == ["note x.md: covers '9.9' is not an id in coverage.json"]


def test_note_covers_unknown_id_is_error(tmp_path):
    (tmp_path / "a.md").write_text("---\ncovers: [1.1, 3.9]\n---\n", encoding="utf-8")
    coverage, cards = load()
    report, errors = cov.compute(coverage, cards, tmp_path)
    assert any("a.md" in e and "3.9" in e for e in errors)
    assert report["domains"][0]["tasks"][0]["notes"] == ["a"]


def test_example_report():
    coverage, cards = load()
    report, errors = cov.compute(coverage, cards, EX / "notes")
    assert errors == []
    t = report["domains"][0]["tasks"][0]
    assert t["id"] == "1.1" and t["cards"] == 1 and t["p1"] == 1 and t["notes"] == ["intro"] and t["status"] == "green"
    s = report["services"][0]
    assert s["id"] == "svc:thing" and s["cards"] == 1 and s["notes"] == [] and s["status"] == "yellow"
    c = report["concepts"][0]
    assert c["id"] == "concept:apis" and c["cards"] == 0 and c["status"] == "red"
    assert report["summary"] == {
        "tasks": {"total": 1, "green": 1, "yellow": 0, "red": 0},
        "services": {"total": 1, "green": 0, "yellow": 1, "red": 0},
        "concepts": {"total": 1, "green": 0, "yellow": 0, "red": 1}}


def test_status_and_summary(tmp_path):
    # cards but no note -> yellow, and the summary counts what the rows say
    coverage, cards = load()
    report, _ = cov.compute(coverage, cards, tmp_path)   # empty notes dir
    assert report["domains"][0]["tasks"][0]["status"] == "yellow"
    rows = [t for d in report["domains"] for t in d["tasks"]]
    assert report["summary"]["tasks"]["yellow"] == sum(r["status"] == "yellow" for r in rows) == 1


def test_cards_without_covers_count_nowhere():
    coverage, cards = load()
    for c in cards:
        c.pop("covers", None)
    report, _ = cov.compute(coverage, cards, EX / "notes")
    assert all(r["cards"] == 0 for r in report["services"] + report["concepts"])
    assert report["domains"][0]["tasks"][0]["cards"] == 0


def test_rows_keep_guide_fields():
    coverage, cards = load()
    report, _ = cov.compute(coverage, cards, EX / "notes")
    t = report["domains"][0]["tasks"][0]
    assert t["title"] == "Know the basics." and t["skills"] == ["Naming the basics"]
    assert report["domains"][0]["weight"] == 100


def test_summary_lines_name_red_tasks(tmp_path):
    coverage, cards = load()
    cards2 = copy.deepcopy(cards)
    for c in cards2:
        c.pop("covers", None)
    report, _ = cov.compute(coverage, cards2, tmp_path)
    lines = cov.summary_lines(report)
    assert lines[0].startswith("   coverage tasks") and "0 green / 0 yellow / 1 red of 1" in lines[0]
    assert lines[-1] == "   tasks without card or note: 1.1"
