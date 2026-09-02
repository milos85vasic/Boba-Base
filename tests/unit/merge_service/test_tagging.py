"""RED-first tests for content-derived qBittorrent tags.

WHY THIS EXISTS (measured 2026-09-01): the live qBittorrent instance carried 18
tags, ALL of them test pollution — `boba-bridge-{go,red,neg}-<uuid>` minted by
tests/integration/test_webui_bridge_auth_live.py which never cleaned up, plus
two ad-hoc probe tags. Meanwhile every REAL torrent had `tags=''` and
`category=''`. There was no `tags` field in any torrent-add path at all.

The metadata to tag properly already existed and was simply never wired in:
MetadataEnricher supplies content_type / year / genres, and detect_quality()
parses the resolution/source/codec tier straight out of the torrent name with
no external API.

Operator decision (2026-09-01): tag with content type + quality + year + genre,
and carry BOTH promotion tags "Boba" and "Боба". Source tracker was explicitly
NOT selected.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# House pattern (matches tests/unit/merge_service/test_enricher.py): load the
# module by file location. `merge_service` is one of conftest's _POLLUTING_ROOTS
# — snapshotted and restored around every unit test — so a plain package import
# is not reliable here.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_MS_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src", "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_tagging_spec = importlib.util.spec_from_file_location(
    "merge_service.tagging", os.path.join(_MS_PATH, "tagging.py")
)
_tagging_mod = importlib.util.module_from_spec(_tagging_spec)
sys.modules["merge_service.tagging"] = _tagging_mod
_tagging_spec.loader.exec_module(_tagging_mod)

MAX_GENRE_TAGS = _tagging_mod.MAX_GENRE_TAGS
PROMO_TAGS = _tagging_mod.PROMO_TAGS
build_tags = _tagging_mod.build_tags
tags_to_qbittorrent_field = _tagging_mod.tags_to_qbittorrent_field


class TestPromoTags:
    def test_both_promo_tags_always_present(self):
        """The operator chose BOTH Latin and Cyrillic promo tags."""
        tags = build_tags(name="Some.Movie.2020.1080p.BluRay.x264")
        assert "Boba" in tags
        assert "Боба" in tags

    def test_promo_tags_present_even_with_no_derivable_metadata(self):
        """A hash-named torrent yields no content tags — promo must still apply."""
        tags = build_tags(name="51fe5ac2ef44ee6b2cc08478bb81ac4b54b826a8")
        assert set(PROMO_TAGS).issubset(set(tags))

    def test_promo_tags_are_exactly_the_two_agreed(self):
        assert PROMO_TAGS == ("Boba", "Боба")


class TestQualityTags:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Movie.2020.2160p.WEB-DL.x265", "4K"),
            ("Movie.2020.1080p.BluRay", "1080p"),
            ("Movie.2020.720p.HDRip", "720p"),
            ("Movie.2020.BDRip.x264", "BluRay"),
            ("Show.S01E01.HDTV.x264", "HDTV"),
        ],
    )
    def test_quality_is_derived_from_the_name_alone(self, name, expected):
        """Quality needs no external API — it must work fully offline."""
        assert expected in build_tags(name=name)

    def test_unparseable_name_yields_no_quality_tag(self):
        """Never invent a quality tier that the name does not support (§11.4.6)."""
        tags = build_tags(name="Some Random Release Name")
        for q in ("4K", "1080p", "720p", "SD", "BluRay", "WEB-DL", "HDTV", "DVD"):
            assert q not in tags


class TestContentTypeAndYearAndGenre:
    def test_content_type_is_tagged_and_normalised(self):
        tags = build_tags(name="X.1080p", content_type="movie")
        assert "Movie" in tags

    def test_year_is_tagged_as_a_plain_string(self):
        assert "1994" in build_tags(name="The Lion King 1080p", year=1994)

    def test_genres_are_tagged(self):
        tags = build_tags(name="X.1080p", genres=["Animation", "Family"])
        assert "Animation" in tags and "Family" in tags

    def test_genres_are_capped_to_avoid_tag_sidebar_noise(self):
        many = [f"Genre{i}" for i in range(20)]
        tags = build_tags(name="X.1080p", genres=many)
        applied = [t for t in tags if t.startswith("Genre")]
        assert len(applied) == MAX_GENRE_TAGS

    def test_absent_metadata_is_simply_omitted_never_guessed(self):
        """No external lookup -> no type/year/genre tags. Not 'Unknown'."""
        tags = build_tags(name="Movie.1080p.BluRay")
        assert "Unknown" not in tags
        assert not any(t.isdigit() and len(t) == 4 for t in tags)


class TestSanitisation:
    def test_commas_are_stripped_because_the_api_field_is_comma_separated(self):
        """A comma inside a tag would split it into two bogus tags at the API."""
        tags = build_tags(name="X.1080p", genres=["Action, Adventure"])
        assert all("," not in t for t in tags)

    def test_no_empty_or_whitespace_only_tags(self):
        tags = build_tags(name="X.1080p", genres=["", "   ", "Drama"])
        assert all(t.strip() for t in tags)
        assert "Drama" in tags

    def test_tags_are_deduplicated_preserving_order(self):
        tags = build_tags(name="X.1080p", genres=["Drama", "Drama"])
        assert len(tags) == len(set(tags))

    def test_field_serialisation_is_comma_separated(self):
        field = tags_to_qbittorrent_field(["Movie", "1080p", "Boba"])
        assert field == "Movie,1080p,Boba"

    def test_serialising_empty_list_yields_empty_string(self):
        assert tags_to_qbittorrent_field([]) == ""


class TestNoTestPollutionShape:
    """Regression guard for the actual defect that prompted this work."""

    def test_no_generated_tag_uses_the_boba_hyphen_prefix(self):
        """`boba-bridge-*` / `boba-py-proof` were test artefacts, never a scheme.

        The promo tags are exactly "Boba"/"Боба" — no hyphenated variants, and
        nothing uuid-suffixed. If a future change reintroduces a `boba-...`
        shape from production code this fails.
        """
        tags = build_tags(
            name="Movie.2020.1080p.BluRay",
            content_type="movie",
            year=2020,
            genres=["Drama"],
        )
        assert not any(t.lower().startswith("boba-") for t in tags)
