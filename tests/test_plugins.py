"""The plugin hook of `./build.py check` (build/plugins.py): config `checks` and
`checks-disable`, the `run(book, labels)` protocol, `engine:<name>` tools."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FixtureBookCase, run_build  # noqa: E402

# A book plugin that imports a sibling module, the way book tools do.
HELPER = '''def count(labels):
    return len(labels)
'''
PLUGIN = '''from plugin_helper import count


def run(book, labels, options=None):
    word = (options or {}).get("word", "labels")
    return [f"{book.title} has {count(labels)} {word}"], ["a note from the plugin"]
'''
PAIR_ONLY = '''def find_violations(labels):
    return sorted(labels)[:1]


def report(violations):
    return "\\n".join(f"pair-only saw {v}" for v in violations)
'''
CRASHES = '''def run(book, labels):
    raise ValueError("boom")
'''

# The fixture with its broken reference removed and a forward proof citation added, so the
# default forward-deps gate has something to report (and to be disabled).
FORWARD = ("Immediate from @def-thing.", "Immediate from @def-thing and @thm-area.")


def configure(book_dir: Path, **keys):
    config = json.loads((book_dir / "book.json").read_text())
    config.update(keys)
    (book_dir / "book.json").write_text(json.dumps(config, indent=2))


def prepare_book(book_dir: Path):
    refs = book_dir / "src" / "ch02-more" / "01-refs.md"
    refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
    second = book_dir / "src" / "ch01-basics" / "02-second.md"
    second.write_text(second.read_text().replace(*FORWARD))
    tools = book_dir / "tools"
    tools.mkdir()
    (tools / "plugin_helper.py").write_text(HELPER)
    (tools / "my_check.py").write_text(PLUGIN)
    (tools / "pair_only.py").write_text(PAIR_ONLY)
    (tools / "crashes.py").write_text(CRASHES)


class TestBookPlugins(FixtureBookCase):

    @classmethod
    def prepare(cls, book_dir: Path):
        prepare_book(book_dir)
        configure(book_dir, checks=[
            {"tool": "tools/my_check.py", "options": {"word": "labels in all"}, "prefix": "mine"},
            {"tool": "tools/pair_only.py", "fatal": False},
            {"tool": "tools/not_there.py", "requires": "verify"},      # skipped: no verify/
            "engine:check_rendered",
        ])

    def setUp(self):
        self.result = run_build(self.book_dir, "check")
        self.out = self.result.stdout

    def test_a_fatal_plugin_fails_the_check_with_its_prefix(self):
        self.assertEqual(self.result.returncode, 1)
        self.assertRegex(self.out, r"✖ mine: Fixture Book has \d+ labels in all")
        self.assertIn("⚠ mine: a note from the plugin", self.out)

    def test_a_non_fatal_plugin_only_warns(self):
        self.assertIn("⚠ pair-only saw", self.out)

    def test_requires_skips_and_engine_tools_resolve(self):
        self.assertNotIn("not_there", self.out)
        self.assertNotIn("check_rendered", self.out)    # found, and the fixture renders clean

    def test_the_default_forward_gate_still_runs(self):
        self.assertIn("thm-second cites thm-area in its proof", self.out)


class TestDisableAndFailures(FixtureBookCase):

    @classmethod
    def prepare(cls, book_dir: Path):
        prepare_book(book_dir)
        configure(book_dir, checks=["tools/crashes.py", "tools/missing.py"],
                  **{"checks-disable": ["forward-deps", "spelling", "no-such-check"]})

    def test_disabled_default_and_broken_plugins(self):
        result = run_build(self.book_dir, "check")
        out = result.stdout
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("thm-second cites thm-area", out)          # forward-deps disabled
        self.assertNotIn("spelling in", out)                        # spelling disabled
        self.assertIn("checks: tools/crashes.py failed: ValueError: boom", out)
        self.assertIn("checks: tools/missing.py not found", out)
        self.assertIn("checks-disable: unknown check 'no-such-check'", out)


if __name__ == "__main__":
    unittest.main()
