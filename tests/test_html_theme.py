"""The HTML theme's static files (templates/html): every font the stylesheet names is
shipped, the stylesheet parses as balanced blocks, and the search palette is a combobox."""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "templates" / "html"


class TestHtmlTheme(unittest.TestCase):
    def setUp(self):
        self.css = (HTML / "styles.css").read_text(encoding="utf-8")

    def test_fonts_named_in_the_stylesheet_are_shipped(self):
        names = set(re.findall(r"url\('fonts/([^']+)'\)", self.css))
        self.assertTrue(names)
        for name in names:
            self.assertTrue((HTML / "fonts" / name).is_file(), name)
        for name in (HTML / "fonts").glob("*.woff2"):
            self.assertIn(name.name, names, f"unused font file {name.name}")

    def test_stylesheet_blocks_balance(self):
        text = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
        depth = 0
        for char in text:
            depth += {"{": 1, "}": -1}.get(char, 0)
            self.assertGreaterEqual(depth, 0)
        self.assertEqual(depth, 0)

    def test_palette_is_a_combobox_in_a_dialog(self):
        template = (HTML / "template.html").read_text(encoding="utf-8")
        self.assertRegex(template, r'role="combobox"[^>]*\n?[^>]*aria-controls="palette-list"')
        self.assertIn('role="listbox"', template)
        self.assertIn('aria-keyshortcuts="Meta+K Control+K /"', template)


if __name__ == "__main__":
    unittest.main()
