from __future__ import annotations

import pytest

from backend.app.captions.formatter import display_width, wrap_caption


def wrap(text: str, chars: int = 20, lines: int = 2) -> tuple[str, ...]:
    return wrap_caption(text, chars_per_line=chars, max_lines=lines)


def widths(rendered: tuple[str, ...]) -> list[int]:
    return [display_width(line) for line in rendered]


class TestDisplayWidth:
    def test_fullwidth_counts_as_two(self) -> None:
        assert display_width("你好") == 4
        assert display_width("abc") == 3
        assert display_width("你好a") == 5
        assert display_width("") == 0

    def test_fullwidth_forms_and_punctuation(self) -> None:
        assert display_width("Ａ") == 2
        assert display_width("。") == 2
        assert display_width("，") == 2

    def test_halfwidth_katakana_counts_as_one(self) -> None:
        assert display_width("ｱ") == 1

    def test_ambiguous_width_counts_as_one(self) -> None:
        # East_Asian_Width == 'A'; the choice is fixed here so layout is
        # predictable rather than font-dependent.
        assert display_width("α") == 1


class TestWrapping:
    def test_empty_and_blank_produce_no_lines(self) -> None:
        assert wrap("") == ()
        assert wrap("   ") == ()

    def test_chinese_fills_exactly_n_characters_per_line(self) -> None:
        text = "一二三四五六七八九十壹貳參肆伍"
        assert wrap(text, chars=5, lines=5) == ("一二三四五", "六七八九十", "壹貳參肆伍")

    def test_every_line_respects_the_column_budget(self) -> None:
        text = "今天我們要談談沉默的力量這聽起來很安靜但也非常重要"
        rendered = wrap(text, chars=6, lines=10)
        assert all(width <= 12 for width in widths(rendered))

    def test_mixed_script_lines_share_the_same_visual_width(self) -> None:
        rendered = wrap("今天 temperature 是 25 度", chars=6, lines=10)
        assert all(width <= 12 for width in widths(rendered))
        assert "".join(rendered).replace(" ", "") == "今天temperature是25度".replace(" ", "")

    def test_only_the_last_lines_are_kept(self) -> None:
        text = "一二三四五六七八九十壹貳"
        assert wrap(text, chars=2, lines=2) == ("九十", "壹貳")

    def test_explicit_newline_forces_a_break(self) -> None:
        assert wrap("你好\n再見", chars=10, lines=5) == ("你好", "再見")


class TestPunctuationRules:
    def test_closing_punctuation_never_starts_a_line(self) -> None:
        # "你好嗎" fills the line exactly; the question mark must stay with it
        rendered = wrap("你好嗎？再見", chars=3, lines=5)
        assert rendered[0] == "你好嗎？"
        assert not rendered[1].startswith("？")

    def test_every_closing_mark_is_covered(self) -> None:
        for mark in "。、，；：！？）」』】…":
            rendered = wrap(f"甲乙丙{mark}丁", chars=3, lines=5)
            assert rendered[0].endswith(mark), mark

    def test_opening_punctuation_never_ends_a_line(self) -> None:
        rendered = wrap("甲乙丙「丁戊", chars=4, lines=5)
        assert not rendered[0].endswith("「")
        assert rendered[1].startswith("「")

    def test_overflow_from_punctuation_stays_within_one_fullwidth(self) -> None:
        rendered = wrap("甲乙丙。丁戊己。", chars=3, lines=10)
        assert all(width <= 3 * 2 + 2 for width in widths(rendered))


class TestLatinWords:
    def test_words_break_at_spaces_rather_than_mid_word(self) -> None:
        rendered = wrap("hello wonderful world", chars=6, lines=5)
        assert rendered == ("hello", "wonderful", "world")

    def test_an_oversized_word_is_split_rather_than_looping(self) -> None:
        rendered = wrap("supercalifragilistic", chars=3, lines=10)
        assert all(width <= 6 for width in widths(rendered))
        assert "".join(rendered) == "supercalifragilistic"


class TestInvariants:
    @pytest.mark.parametrize("chars", [1, 2, 5, 20])
    @pytest.mark.parametrize(
        "text",
        [
            "你好",
            "今天我們要談談沉默的力量。",
            "hello world",
            "混合 mixed 12345 內容。",
            "。。。。。",
        ],
    )
    def test_no_content_is_lost_and_budget_holds(self, text: str, chars: int) -> None:
        rendered = wrap(text, chars=chars, lines=50)
        # nothing vanishes except the spaces consumed by wrapping
        assert "".join(rendered).replace(" ", "") == text.replace(" ", "")
        assert all(
            width <= chars * 2 + 2 for width in widths(rendered)
        ), rendered

    def test_never_returns_more_than_max_lines(self) -> None:
        text = "一二三四五六七八九十" * 10
        for max_lines in (1, 2, 5):
            assert len(wrap(text, chars=4, lines=max_lines)) <= max_lines


def test_a_sentence_ending_near_the_edge_pushes_the_next_one_to_a_new_line() -> None:
    # 16 full-width characters then 。 leaves 3 characters of room on a
    # 20-character line: not enough to start a sentence in.
    text = "一二三四五六七八九十一二三四五六。下一句開始"

    lines = wrap_caption(text, chars_per_line=20, max_lines=5)

    assert lines[0] == "一二三四五六七八九十一二三四五六。"
    assert lines[1] == "下一句開始"


def test_a_sentence_ending_early_keeps_the_next_one_on_the_same_line() -> None:
    # Plenty of room left, so breaking would waste most of the line.
    text = "今天天氣很好。我們開始"

    lines = wrap_caption(text, chars_per_line=20, max_lines=5)

    assert lines == ("今天天氣很好。我們開始",)


def test_the_threshold_is_measured_in_remaining_space_not_a_fraction() -> None:
    # On a 60-character line a sentence ending at character 41 still leaves 19
    # characters — a fraction-of-the-line rule would throw those away.
    text = "一二三四五六七八九十" * 4 + "。" + "接著這一句還很長"

    lines = wrap_caption(text, chars_per_line=60, max_lines=5)

    assert lines[0].startswith("一二三四")
    assert "接著這一句還很長" in lines[0]


def test_only_full_width_sentence_marks_count() -> None:
    # A half-width period appears in decimals and abbreviations; treating it
    # as a sentence end would break "3.5 公里" in half.
    text = "距離是 3.5 公里再往前走一點就到了目的地了"

    lines = wrap_caption(text, chars_per_line=8, max_lines=5)

    assert not any(line.endswith("3.") for line in lines)


def test_a_closing_bracket_stays_with_the_sentence_it_ends() -> None:
    text = "他說「我們準備好了。」下一句從這裡開始"

    lines = wrap_caption(text, chars_per_line=12, max_lines=5)

    assert lines[0].endswith("」")


def test_sentence_breaks_can_be_turned_off() -> None:
    text = "一二三四五六七八九十一二三四五六。下一句開始"

    lines = wrap_caption(
        text, chars_per_line=20, max_lines=5, sentence_breaks=False
    )

    assert lines[0] != "一二三四五六七八九十一二三四五六。"


def test_a_sentence_ending_the_text_does_not_leave_a_blank_line() -> None:
    lines = wrap_caption("很長的一句話講完了。", chars_per_line=10, max_lines=5)

    assert lines == ("很長的一句話講完了。",)
