import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gemma  # noqa: E402


def j1(message, line="Fine. I'll look."):
    return json.dumps({"message": message, "spider_line": line})


def test_job1_good_passes():
    assert gemma.validate_job1(j1("HORDE EAST")) == {"message": "HORDE EAST", "spider_line": "Fine. I'll look."}


def test_job1_rejects_lowercase():
    assert gemma.validate_job1(j1("horde east")) is None


def test_job1_rejects_digits():
    assert gemma.validate_job1(j1("HORDE 9")) is None


def test_job1_rejects_three_words():
    assert gemma.validate_job1(j1("ONE TWO SIX")) is None


def test_job1_rejects_eleven_letters():
    assert gemma.validate_job1(j1("ABCDEF GHIJK")) is None


def test_job1_rejects_empty_spider_line():
    assert gemma.validate_job1(j1("HORDE EAST", "")) is None


def test_job1_rejects_bad_json():
    assert gemma.validate_job1("{not json") is None


def j2(scene, reaction="Oh no. Humans."):
    return json.dumps({"scene": scene, "reaction": reaction})


def test_job2_good_passes():
    r = gemma.validate_job2(j2("Two humans to the left, about one metre away."), "FEW", "left")
    assert r and r["scene"].startswith("Two")


def test_job2_rejects_banned_words():
    assert gemma.validate_job2(j2("A human with a face to the left."), "FEW", "left") is None
    assert gemma.validate_job2(j2("Human to the left."), "FEW", "left") is not None


def test_job2_few_needs_side_word():
    assert gemma.validate_job2(j2("Two humans somewhere nearby."), "FEW", "left") is None
    assert gemma.validate_job2(j2("Two humans in front of me."), "FEW", "ahead") is not None


def test_job2_clear_needs_no_side_word():
    assert gemma.validate_job2(j2("Nothing in range."), "CLEAR", "ahead") is not None


def test_job2_rejects_over_length():
    long_scene = " ".join(["left"] * 31)
    assert gemma.validate_job2(j2(long_scene), "FEW", "left") is None
    long_react = " ".join(["no"] * 21)
    assert gemma.validate_job2(j2("Human to the left.", long_react), "FEW", "left") is None


def test_job2_rejects_bad_json():
    assert gemma.validate_job2("nope", "FEW", "left") is None
