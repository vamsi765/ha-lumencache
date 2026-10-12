"""strings.json is the source and translations/en.json is what Home Assistant loads. They must say the same."""
import json
from pathlib import Path

INTEGRATION = Path(__file__).parent.parent / "custom_components" / "lumencache"


def test_english_translations_match_strings():
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8"))
    assert english == strings
