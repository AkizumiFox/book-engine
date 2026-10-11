"""Every proof must belong to a result the dependency scanner can see.

The scanner credits a proof to the labeled result before it, and resets at every
heading. A proof placed under its own heading, after the lemmas it uses, belonged
to nothing: the proofs of the fundamental theorem of algebra and of Cayley-Hamilton
were invisible to the forward-dependency gate this way. Such a proof must name its
result with `::: {.proof of="thm-..."}`.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bookenv import SRC  # noqa: E402
# A statement's div may carry classes beside its id (`{#thm-foo .optional}`), and a
# proof after one still belongs to it.
LABEL = re.compile(r'^:{3,}\s*\{#((thm|lem|prp|cor|cnj|def|exm|exr|ax)-[a-z0-9-]+)(\s+\.[a-z0-9-]+)*\s*\}')
PROOF = re.compile(r'^:{3,}\s*\{\.proof(\s+of="([a-z0-9-]+)")?\s*\}')


class TestProofOwnership(unittest.TestCase):

    def test_no_orphan_proofs(self):
        orphans = []
        for md in sorted(SRC.rglob("*.md")):
            current = None
            for number, line in enumerate(md.read_text().split("\n"), 1):
                if re.match(r'^#{1,6} ', line):
                    current = None
                    continue
                label = LABEL.match(line)
                if label:
                    current = label.group(1)
                    continue
                proof = PROOF.match(line)
                if proof and current is None and not proof.group(2):
                    orphans.append(f"{md.relative_to(SRC)}:{number}")
        self.assertEqual(orphans, [], 'a proof after a heading needs {.proof of="thm-..."}')

    def test_named_owners_exist(self):
        labels = set()
        named = []
        for md in SRC.rglob("*.md"):
            text = md.read_text()
            labels.update(re.findall(r'\{#([a-z]+-[a-z0-9-]+)(?:\s+\.[a-z0-9-]+)*\s*\}', text))
            named += [(md.relative_to(SRC), m) for m in re.findall(r'\{\.proof\s+of="([a-z0-9-]+)"\}', text)]
        missing = [f"{path}: {m}" for path, m in named if m not in labels]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
