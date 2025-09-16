from ocr_core.confidence import parse

def test_percent_string():
    assert parse("87%") == 0.87

def test_float_and_int():
    assert parse(0.5) == 0.5
    assert parse(87) == 0.87

def test_invalid():
    assert parse("abc") is None
    assert parse(None) is None
