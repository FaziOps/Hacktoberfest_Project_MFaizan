import pytest

from app.core import fabric_core as fc


def test_parse_model_json_handles_fences_and_chatter():
    assert fc.parse_model_json('```json\n{"defects": []}\n```') == {"defects": []}
    assert fc.parse_model_json('Here you go: {"a": 1} hope it helps') == {"a": 1}
    with pytest.raises(ValueError):
        fc.parse_model_json("no json here")


def test_normalize_scores_and_cleans_defects():
    raw = {
        "image_quality": "good",
        "fabric": "white cotton",
        "defects": [
            {"type": "stain", "size": "3_to_6in", "location": "centre", "confidence": 0.9, "description": "oil"},
            {"type": "hole", "size": "up_to_3in", "location": "left", "confidence": 0.8, "description": ""},
            {"type": "weird", "size": "huge", "location": "", "confidence": 2, "description": ""},
            {"type": "slub", "size": "up_to_3in", "location": "", "confidence": 0.1, "description": "noise"},
        ],
    }
    result = fc.normalize(raw)
    types = [d["type"] for d in result["defects"]]
    assert types == ["stain", "hole", "other"]  # low-confidence slub dropped
    assert [d["points"] for d in result["defects"]] == [2, 4, 1]  # hole always 4
    assert result["points"] == 7
    assert result["defects"][2]["confidence"] == 1.0
    assert result["defects"][0]["name_ur"] == "داغ"


def test_normalize_falls_back_on_bad_quality_value():
    assert fc.normalize({"image_quality": "???", "defects": None})["image_quality"] == "good"


def test_roll_score_matches_4_point_formula():
    # 150 cm = 59.06 in, 10 m = 10.94 yd: 8 points -> 8 * 3600 / (59.06 * 10.94) = 44.6
    assert fc.roll_score(8, 150, 10) == 44.6
    with pytest.raises(ValueError):
        fc.roll_score(1, 0, 10)


@pytest.mark.parametrize("score, letter", [(0, "A"), (20, "A"), (20.1, "B"), (40, "B"), (40.1, "C")])
def test_grade_boundaries(score, letter):
    assert fc.grade(score) == letter


def test_summarize_roll_writes_both_languages():
    defects = [{"type": "stain", "points": 2}, {"type": "stain", "points": 1}, {"type": "hole", "points": 4}]
    summary = fc.summarize_roll("R-14", defects, 150, 10)
    assert summary["total_points"] == 7
    assert summary["grade"] == "B"
    assert "2 stain / oil spot" in summary["english"]
    assert "2 داغ" in summary["urdu"]
    assert summary["counts"] == {"stain": 2, "hole": 1}


def test_ollama_payload_disables_thinking_and_sets_schema():
    payload = fc.build_ollama_payload("gemma4:latest", "hi", ["abc"], fc.RESPONSE_SCHEMA)
    assert payload["think"] is False
    assert payload["format"] is fc.RESPONSE_SCHEMA
    assert payload["messages"][0]["images"] == ["abc"]
