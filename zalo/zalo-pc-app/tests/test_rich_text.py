"""rich_text: định dạng chữ Zalo (đậm, nghiêng, màu, cỡ, danh sách) theo khoảng UTF-16, tự nhấn mạnh số, kiểm tra đầu vào."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from zalo_pc_app import rich_text as R  # noqa: E402


def st_of(styles, plain, token):
    """Các đoạn chữ mang mã style `token` (đọc ngược khoảng UTF-16 về chuỗi để kiểm đúng vị trí)."""
    u = plain.encode("utf-16-le")
    return [u[s["start"] * 2:(s["start"] + s["len"]) * 2].decode("utf-16-le")
            for s in styles if token in s["st"].split(",")]


class RichTextTests(unittest.TestCase):
    def test_example_from_old_zalo_readme(self):
        # README zalo_bot: "Nhiệt độ 29°C" -> start 9, len 4 (29°C)
        plain, styles = R.render("Nhiệt độ **29°C**", "markdown")
        self.assertEqual(plain, "Nhiệt độ 29°C")
        self.assertEqual(styles, [{"start": 9, "len": 4, "st": "b"}])

    def test_offsets_are_utf16_so_emoji_counts_two(self):
        plain, styles = R.render("😀 **đậm** sau", "markdown")
        self.assertEqual(styles[0]["start"], 3)
        self.assertEqual(st_of(styles, plain, "b"), ["đậm"])

    def test_every_basic_style_color_and_size(self):
        plain, styles = R.render("**a** *b* __c__ ~~d~~ {red}e{/} {cam}f{/} {vàng}g{/} {xanh}h{/} {big}i{/} {nhỏ}k{/}", "markdown")
        self.assertEqual(plain, "a b c d e f g h i k")
        for token, want in (("b", "a"), ("i", "b"), ("u", "c"), ("s", "d"), ("c_db342e", "e"), ("c_f27806", "f"),
                            ("c_f7b503", "g"), ("c_15a85f", "h"), ("f_18", "i"), ("f_13", "k")):
            self.assertEqual(st_of(styles, plain, token), [want], token)

    def test_nested_styles_merge_into_one_run_with_combined_code(self):
        plain, styles = R.render("# Tiêu đề", "markdown")
        self.assertEqual(styles, [{"start": 0, "len": 7, "st": "f_18,b"}])
        plain, styles = R.render("{red}**x**{/}", "markdown")
        self.assertEqual(styles, [{"start": 0, "len": 1, "st": "c_db342e,b"}])

    def test_lists_are_whole_line_ranges_not_split_by_inline_styles(self):
        plain, styles = R.render("- {red}Cửa mở{/} lúc 15:30\n1. hai", "markdown")
        self.assertEqual(plain, "Cửa mở lúc 15:30\nhai")
        lst = [s for s in styles if s["st"].startswith("lst_")]
        self.assertEqual(lst, [{"start": 0, "len": 16, "st": "lst_1"}, {"start": 17, "len": 3, "st": "lst_2"}])

    def test_unpaired_or_in_word_markers_stay_literal(self):
        for text in ("snake_case_name", "2 * 3 = 6", "giá 5**", "{red}không đóng", "{lạ}x{/}", "a ~~ b"):
            plain, styles = R.render(text, "markdown")
            self.assertEqual((plain, styles), (text, []), text)

    def test_backslash_escapes_marker(self):
        plain, styles = R.render(r"\*\*không đậm\*\*", "markdown")
        self.assertEqual((plain, styles), ("**không đậm**", []))

    def test_plain_text_is_untouched_without_options(self):
        self.assertEqual(R.render("**vẫn nguyên** 29°C"), ("**vẫn nguyên** 29°C", []))

    def test_auto_emphasis_colors_numbers_with_attached_units_by_syntax_not_keywords(self):
        plain, styles = R.render("Nhiệt độ 29°C, ẩm 75%, 10 và 20, lúc 15:30 ngày 10/11", "plain", emphasis=True)
        self.assertEqual(st_of(styles, plain, "c_db342e"), ["29°C", "75%", "10", "20", "15:30", "10/11"])
        self.assertTrue(all(s["st"] == "c_db342e,b" for s in styles))
        self.assertNotIn("và", st_of(styles, plain, "b"))

    def test_auto_emphasis_color_choice_and_bold_markdown_gets_color_but_explicit_color_wins(self):
        plain, styles = R.render("**quan trọng** {green}ổn 5{/} 7", "markdown", emphasis="cam")
        self.assertEqual(st_of(styles, plain, "c_f27806"), ["quan trọng", "7"])
        self.assertEqual(st_of(styles, plain, "c_15a85f"), ["ổn 5"])

    def test_normalize_emphasis(self):
        for v, want in ((None, None), (False, None), ("", None), ("off", None), (True, "red"), ("true", "red"), ("đỏ", "red"),
                        ("xanh", "green"), ("Orange", "orange")):
            self.assertEqual(R.normalize_emphasis(v), want, v)
        with self.assertRaises(ValueError):
            R.normalize_emphasis("tím")

    def test_validate_styles_rejects_what_zalo_would_silently_ignore(self):
        ok = R.validate_styles("Nhiệt độ 29°C", [{"start": 9, "len": 4, "st": "f_18,c_db342e,b"}])
        self.assertEqual(ok[0]["st"], "f_18,c_db342e,b")
        for bad in ([{"start": 0, "len": 3, "st": "f_20"}],             # cỡ chữ không có
                    [{"start": 0, "len": 3, "st": "c_ffffff"}],        # màu không có
                    [{"start": 12, "len": 5, "st": "b"}],              # vượt nội dung
                    [{"start": -1, "len": 2, "st": "b"}], [{"start": 0, "len": 0, "st": "b"}],
                    [{"start": 0, "len": 2}], "b", [{"start": "x", "len": 2, "st": "b"}]):
            with self.assertRaises(ValueError, msg=str(bad)):
                R.validate_styles("Nhiệt độ 29°C", bad)
        self.assertEqual(R.validate_styles("abc", [{"start": 0, "len": 3, "st": "ind_20"}])[0]["st"], "ind_20")

    def test_self_computed_styles_cannot_mix_with_markdown_or_emphasis(self):
        with self.assertRaises(ValueError):
            R.render("abc", "markdown", styles=[{"start": 0, "len": 1, "st": "b"}])
        with self.assertRaises(ValueError):
            R.render("abc", "plain", emphasis=True, styles=[{"start": 0, "len": 1, "st": "b"}])
        self.assertEqual(R.render("abc", styles=[{"start": 0, "len": 1, "st": "b"}])[1], [{"start": 0, "len": 1, "st": "b"}])

    def test_text_properties_matches_zca_js_shape(self):
        self.assertEqual(R.text_properties([{"start": 9, "len": 4, "st": "b"}]),
                         '{"styles":[{"start":9,"len":4,"st":"b"}],"ver":0}')

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError):
            R.render("a", "html")

    # ---- emoji ----
    def test_shortcodes_expand_only_known_names(self):
        self.assertEqual(R.render("Xong :ok: và :lạ: :khong_co:", "markdown")[0], "Xong ✅ và :lạ: :khong_co:")
        self.assertEqual(R.render("giờ 10:30:45 ok", "markdown")[0], "giờ 10:30:45 ok")        # không nuốt dấu hai chấm của giờ

    def test_emoji_prefix_by_name_or_literal_and_goes_after_heading_marker(self):
        self.assertEqual(R.render("xong", emoji="ok")[0], "✅ xong")
        self.assertEqual(R.render("xong", emoji=":ok:")[0], "✅ xong")
        self.assertEqual(R.render("xong", emoji="🎉")[0], "🎉 xong")
        plain, styles = R.render("# Tiêu đề", "markdown", emoji="alert")
        self.assertEqual(plain, "🚨 Tiêu đề")
        self.assertEqual(styles, [{"start": 0, "len": 10, "st": "f_18,b"}])        # emoji (2 đơn vị UTF-16) nằm trong khoảng to + đậm

    def test_bad_emoji_rejected(self):
        for bad in ("abc", "ok1", "x" * 3, "🎉" * 9):
            with self.assertRaises(ValueError, msg=bad):
                R.normalize_emoji(bad)
        self.assertIsNone(R.normalize_emoji(""))
        self.assertIsNone(R.normalize_emoji(None))

    def test_auto_emoji_is_conservative_one_per_line_start_and_skips_lines_with_emoji(self):
        out = R.render("Cảnh báo: cửa mở\nNhiệt độ 29°C\nbình thường\n✅ đã xong\n\n- Đã tắt đèn", auto_emoji=True)[0]
        self.assertEqual(out, "🚨 Cảnh báo: cửa mở\n🌡️ Nhiệt độ 29°C\nbình thường\n✅ đã xong\n\n- ✅ Đã tắt đèn")
        self.assertEqual(R.render("Cảnh báo", auto_emoji=False)[0], "Cảnh báo")             # mặc định tắt
        self.assertEqual(R.render("cửahàng", auto_emoji=True)[0], "cửahàng")                # chỉ khớp nguyên từ

    def test_offsets_stay_correct_with_emoji_before_styled_text(self):
        plain, styles = R.render("Cửa mở lúc 15:30", emphasis=True, auto_emoji=True)
        self.assertEqual(plain, "🚪 Cửa mở lúc 15:30")
        self.assertEqual(st_of(styles, plain, "b"), ["15:30"])

    def test_self_computed_styles_cannot_mix_with_emoji(self):
        for kw in (dict(emoji="ok"), dict(auto_emoji=True)):
            with self.assertRaises(ValueError):
                R.render("abc", styles=[{"start": 0, "len": 1, "st": "b"}], **kw)

    def test_emoji_table_has_no_duplicate_ascii_names_clash_and_picker_is_unique(self):
        self.assertTrue(all(R.EMOJI[k] for k in R.EMOJI))
        self.assertEqual(R.normalize_emoji("nhietdo"), R.normalize_emoji("temp"))


if __name__ == "__main__":
    unittest.main()
