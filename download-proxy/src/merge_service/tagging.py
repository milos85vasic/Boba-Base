"""Content-derived qBittorrent tags.

WHY THIS MODULE EXISTS (measured 2026-09-01)
--------------------------------------------
The live qBittorrent instance carried 18 tags, every one of them test
pollution — `boba-bridge-{go,red,neg}-<uuid>` minted by an integration test
that never cleaned up after itself (§11.4.14), plus two ad-hoc probe tags.
Meanwhile every REAL torrent had ``tags=''`` and ``category=''``: there was no
``tags`` field in ANY torrent-add path, in either the Python proxy, the
webui-bridge, or the Go client.

So the `boba-...` strings the operator saw were never a tagging scheme. They
were debris. This module supplies the scheme that was missing.

The metadata was already available and simply never reached the add call:

* :class:`merge_service.enricher.MetadataEnricher` resolves ``content_type``,
  ``year`` and ``genres`` from TMDB/OMDb/TVMaze/AniList/OpenLibrary/MusicBrainz.
* :meth:`MetadataEnricher.detect_quality` parses the resolution / source /
  codec tier straight out of the torrent NAME — no external API, works fully
  offline, and therefore never blocks an add.

OPERATOR DECISION (2026-09-01)
------------------------------
Tag dimensions: content type, quality, year, genre.
Promotion tags: BOTH ``Boba`` and ``Боба``.
Source tracker was explicitly NOT selected as a tag dimension.
Applies to NEW downloads only; existing torrents are not backfilled.

DESIGN RULES
------------
* **Never invent a value** (§11.4.6). Metadata that did not resolve produces no
  tag at all — not ``Unknown``, not a placeholder. An absent tag is honest; a
  fabricated one silently corrupts the operator's library.
* **Never emit a ``boba-`` prefixed tag.** That shape is what the test debris
  used and is reserved as a defect signature.
* **Sanitise for the transport.** qBittorrent's ``tags`` field is a
  COMMA-SEPARATED string, so a comma inside a tag silently splits it into two
  bogus tags. Commas are stripped, not escaped.
* **Cap the genre count.** An unbounded genre list turns the qBittorrent tag
  sidebar into noise, which is the usability problem this work set out to fix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable, Sequence

__all__ = [
    "MAX_GENRE_TAGS",
    "PROMO_TAGS",
    "build_tags",
    "tags_to_qbittorrent_field",
]

#: Both promotion tags, per the operator's decision. Latin first so the tag
#: sidebar groups them predictably in a Latin-sorted locale.
PROMO_TAGS: tuple[str, ...] = ("Boba", "Боба")

#: Genre tags are capped: an unbounded list is exactly the sidebar noise this
#: work exists to remove.
MAX_GENRE_TAGS = 3

#: M-b (review 2026-09-01): cap a single tag's length. The caller-supplied
#: title/genres are otherwise unbounded, so an authenticated caller could mint a
#: megabyte-long tag name into the operator's qBittorrent sidebar.
MAX_TAG_LENGTH = 100

#: Normalised display forms for the enricher's ``content_type`` vocabulary
#: (``movie``, ``tv``, ``music``, ``book``). Anything outside this map is
#: title-cased rather than dropped, so a new upstream type still tags sensibly.
_CONTENT_TYPE_LABELS = {
    "movie": "Movie",
    "film": "Movie",
    "tv": "TV",
    "series": "TV",
    "show": "TV",
    "anime": "Anime",
    "music": "Music",
    "album": "Music",
    "book": "Book",
    "audiobook": "Audiobook",
    "game": "Game",
    "software": "Software",
}

_enricher_singleton = None


def _detect_quality(name: str) -> str | None:
    """Return the quality tier for ``name``, or ``None`` if undeterminable.

    Delegates to :meth:`MetadataEnricher.detect_quality` rather than
    reimplementing the pattern set. Duplicating it here would be the
    byte-identical fork §11.4.251 forbids, and would drift the moment either
    copy learned a new codec.

    The enricher is constructed lazily and reused: its ``__init__`` only reads
    optional API-key env vars, so this performs no I/O.
    """
    global _enricher_singleton
    if not name:
        return None
    try:
        if _enricher_singleton is None:
            from merge_service.enricher import MetadataEnricher

            _enricher_singleton = MetadataEnricher()
        return _enricher_singleton.detect_quality(name)
    except Exception:  # pragma: no cover - defensive
        # Tagging must NEVER block a download. A quality tag is a nice-to-have;
        # failing the add because we could not parse a filename would be a far
        # worse outcome than an untagged torrent.
        return None


def _sanitise(tag: object) -> str | None:
    """Normalise one candidate tag, or return ``None`` if it is unusable.

    Commas are REMOVED rather than escaped: qBittorrent's ``tags`` parameter is
    a comma-separated list with no escape syntax, so a comma inside a tag is
    indistinguishable from a separator and would silently create two wrong tags.
    """
    if tag is None:
        return None
    text = str(tag).replace(",", " ")
    # Collapse internal whitespace so "Action   Adventure" is one clean tag.
    # str.split() also collapses \r, \n and \t, which closes header/multipart
    # injection through a hostile genre string.
    text = " ".join(text.split())
    if not text:
        return None
    # M-b: truncate rather than reject — a long title should still yield a
    # usable tag, just not an abusive one.
    return text[:MAX_TAG_LENGTH]


def build_tags(
    name: str,
    *,
    content_type: str | None = None,
    year: int | None = None,
    genres: Iterable[str] | None = None,
    include_promo: bool = True,
) -> list[str]:
    """Build the tag list for a torrent that is about to be added.

    :param name: the torrent name — the only REQUIRED input, and the one that
        needs no network. Quality is parsed from it.
    :param content_type: ``MetadataResult.content_type`` when a lookup resolved.
    :param year: ``MetadataResult.year`` when a lookup resolved.
    :param genres: ``MetadataResult.genres`` when a lookup resolved.
    :param include_promo: attach the :data:`PROMO_TAGS`. Defaults to True.
    :returns: de-duplicated tags in a stable order — content type, quality,
        year, genres, then promotion tags.

    Every metadata argument is optional by design: an add must succeed with the
    name alone. Anything that did not resolve contributes nothing (§11.4.6) —
    this function never emits a placeholder.
    """
    candidates: list[str | None] = []

    if content_type:
        key = str(content_type).strip().lower()
        candidates.append(_CONTENT_TYPE_LABELS.get(key, str(content_type).strip().title()))

    candidates.append(_detect_quality(name))

    if year:
        # Guard against a bogus upstream year rather than tagging nonsense.
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            year_int = 0
        if 1800 < year_int < 2200:
            candidates.append(str(year_int))

    if genres:
        applied = 0
        for genre in genres:
            if applied >= MAX_GENRE_TAGS:
                break
            cleaned = _sanitise(genre)
            if cleaned:
                candidates.append(cleaned)
                applied += 1

    if include_promo:
        candidates.extend(PROMO_TAGS)

    # De-duplicate while preserving the order above (dict keeps insertion order).
    seen: dict[str, None] = {}
    for candidate in candidates:
        cleaned = _sanitise(candidate)
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)


def tags_to_qbittorrent_field(tags: Sequence[str]) -> str:
    """Serialise ``tags`` for qBittorrent's comma-separated ``tags`` parameter.

    Returns an empty string for an empty list, which qBittorrent treats as
    "no tags" — the correct no-op rather than a tag literally named "".
    """
    return ",".join(t for t in (_sanitise(t) for t in tags) if t)
