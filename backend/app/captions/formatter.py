from __future__ import annotations

import unicodedata

# Marks that must not open a line: a caption that starts with 。 or 」 reads
# as a typesetting mistake.
_NO_LINE_START = frozenset("。、，；：！？）」』】〕》〉·…—～%!?,.:;)]}")

# Marks that must not close a line; they belong with what follows.
_NO_LINE_END = frozenset("（「『【〔《〈([{")

_WIDE = frozenset("WF")

# One full-width character may overflow the budget so a closing mark can stay
# on its own line; this keeps the guarantee bounded and testable.
_PUNCTUATION_OVERFLOW = 2

# Sentence ends, full-width only. A half-width "." appears in decimals and
# abbreviations ("3.5 公里", "Mr. Chen"), and translated output is Traditional
# Chinese, so accepting it would split numbers far more often than sentences.
_SENTENCE_END = frozenset("。！？")

# Marks that belong to the sentence they follow: 「…。」 ends after the quote.
_SENTENCE_TRAILING = frozenset("」』）】》〉”’\"'")

# A sentence starting with less than this much room left gets a line of its
# own. Measured in remaining full-width characters rather than as a fraction
# of the line: at 60 characters per line, "past two thirds" would abandon up
# to 20 characters of usable space.
SENTENCE_BREAK_MIN_CHARS = 4


def display_width(text: str) -> int:
    """Return the caption width of ``text`` in display columns.

    Full-width and wide characters (CJK, full-width forms, CJK punctuation)
    count as two columns, everything else as one. East_Asian_Width
    ``Ambiguous`` counts as one: the true width depends on the font, and a
    fixed choice keeps layout predictable.
    """
    return sum(
        2 if unicodedata.east_asian_width(char) in _WIDE else 1 for char in text
    )


def _is_breakable_before(char: str) -> bool:
    """Latin words stay whole; CJK may break between any two characters."""
    return unicodedata.east_asian_width(char) in _WIDE or char.isspace()


def _sentence_cut(text: str, budget: int) -> int | None:
    """Where to end the line so the next sentence is not cramped, if anywhere.

    Only what is already on screen decides this. Whether the *next* sentence
    would fit in the remaining space cannot be used: captions arrive as
    fragments, so that sentence is usually still being typed, and a decision
    that changed as it grew would make finished lines re-break under the
    reader.
    """
    index = 0
    width = 0
    while index < len(text):
        width += display_width(text[index])
        if width > budget:
            return None  # the line fills up before any sentence ends
        if text[index] not in _SENTENCE_END:
            index += 1
            continue

        end = index + 1
        while end < len(text) and text[end] in _SENTENCE_TRAILING:
            trailing = display_width(text[end])
            if width + trailing > budget:
                break
            width += trailing
            end += 1

        if end >= len(text):
            return None  # the sentence ends the caption; nothing to push down
        if budget - width < SENTENCE_BREAK_MIN_CHARS * 2:
            return end
        index = end  # room to spare: keep this sentence's neighbour company
    return None


def _split_line(text: str, budget: int) -> tuple[str, str]:
    """Take one line of at most ``budget`` columns, return (line, remainder)."""
    width = 0
    cut = 0
    for index, char in enumerate(text):
        char_width = display_width(char)
        if width + char_width > budget:
            break
        width += char_width
        cut = index + 1
    else:
        return text, ""

    if cut == 0:
        # A single character wider than the whole budget: emit it rather than
        # loop forever.
        return text[:1], text[1:]

    # A closing mark would open the next line: pull it back, allowing a
    # bounded overflow.
    while cut < len(text) and text[cut] in _NO_LINE_START:
        if display_width(text[: cut + 1]) > budget + _PUNCTUATION_OVERFLOW:
            break
        cut += 1

    # An opening mark would close this line: push it to the next one.
    while cut > 1 and text[cut - 1] in _NO_LINE_END:
        cut -= 1

    # Prefer breaking at a space so Latin words are not split mid-word.
    if cut < len(text) and not _is_breakable_before(text[cut]):
        space = text.rfind(" ", 0, cut)
        if space > 0:
            return text[:space], text[space + 1 :]

    return text[:cut], text[cut:]


def wrap_caption(
    text: str,
    *,
    chars_per_line: int,
    max_lines: int,
    sentence_breaks: bool = True,
) -> tuple[str, ...]:
    """Break ``text`` into display lines and keep the most recent ones.

    ``chars_per_line`` is counted in full-width characters, so a line holds up
    to ``2 * chars_per_line`` columns: pure Chinese gives exactly that many
    characters per line, while mixed scripts fit more characters at the same
    visual width. Closing punctuation may overflow the budget by one
    full-width character rather than start the next line.

    Line breaking works on code points, not grapheme clusters (decided
    2026-08-10): a ZWJ emoji sequence or a combining mark landing exactly on a
    boundary can be split. Caption output is Traditional Chinese, where this
    does not arise; adding grapheme awareness would mean a new dependency.
    """
    if chars_per_line < 1 or max_lines < 1:
        raise ValueError("chars_per_line 與 max_lines 必須大於 0。")
    if not text.strip():
        return ()

    budget = chars_per_line * 2
    lines: list[str] = []
    for paragraph in text.split("\n"):
        remainder = paragraph.strip()
        while remainder:
            cut = _sentence_cut(remainder, budget) if sentence_breaks else None
            if cut is None:
                line, remainder = _split_line(remainder, budget)
            else:
                line, remainder = remainder[:cut], remainder[cut:]
            lines.append(line.rstrip())
            remainder = remainder.lstrip(" ")

    return tuple(lines[-max_lines:])
