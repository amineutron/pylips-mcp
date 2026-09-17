"""Extraction de l'ID YouTube : la validation protege la commande ADB distante."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import extract_video_id  # noqa: E402


@pytest.mark.parametrize("entree, attendu", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42", "dQw4w9WgXcQ"),
])
def test_ids_valides(entree, attendu):
    assert extract_video_id(entree) == attendu


@pytest.mark.parametrize("entree", [
    "", "pas une url", "https://example.com/video",
    "trop_court", "https://www.youtube.com/watch?v=trop_court",
    "; rm -rf /", "$(reboot)",
])
def test_entrees_refusees(entree):
    assert extract_video_id(entree) is None
