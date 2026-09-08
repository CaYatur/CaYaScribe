import pytest

from cayascribe.offline import assert_local_media


def test_rejects_http():
    with pytest.raises(ValueError):
        assert_local_media("https://example.com/a.mp3")


def test_rejects_unc():
    with pytest.raises(ValueError):
        assert_local_media(r"\\server\share\a.mp3")
