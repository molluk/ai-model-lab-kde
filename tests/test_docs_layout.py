"""Documentation layout, link integrity and installer regression checks."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'

class TestDocumentation(unittest.TestCase):
    def test_docs_consolidated_and_license_at_root(self):
        self.assertTrue((ROOT/'README.md').is_file())
        self.assertTrue((ROOT/'LICENSE').is_file())
        self.assertTrue((ROOT/'NOTICE').is_file())
        self.assertTrue((DOCS/'INDEX.md').is_file())
        self.assertTrue((DOCS/'README_RU.md').is_file())
        self.assertTrue((DOCS/'LOCALIZATION.md').is_file())
        self.assertTrue((DOCS/'BENCHMARKS.md').is_file())
        self.assertEqual(sorted(p.name for p in ROOT.glob('*.md')), ['README.md'])
        self.assertFalse((ROOT/'benchmarks'/'README.md').exists())
        self.assertFalse((ROOT/'locales'/'README.md').exists())

    def test_local_markdown_links_resolve(self):
        for src in [ROOT/'README.md', *DOCS.glob('*.md')]:
            text=src.read_text(encoding='utf-8')
            for link in re.findall(r'\]\(([^)]+)\)',text):
                if link.startswith(('http:', 'https:', 'mailto:', '#', '/')):
                    continue
                target=link.split('#',1)[0]
                if not target or ' ' in target:
                    continue
                dest=(src.parent/target).resolve()
                self.assertTrue(dest.exists(), f'{src.relative_to(ROOT)}: broken link {link}')

    def test_install_uses_docs_directory(self):
        script=(ROOT/'install.sh').read_text(encoding='utf-8')
        self.assertIn('"$SOURCE"/docs/*.md',script)
        self.assertIn('"$DEST/docs/',script)
        self.assertNotIn('"$SOURCE/benchmarks/README.md"',script)
        self.assertNotIn('run.sh README.md README_RU.md',script)

    def test_main_readme_describes_features_not_version_headings(self):
        text=(ROOT/'README.md').read_text(encoding='utf-8')
        for heading in re.findall(r'^#{1,4} (.+)$',text,re.M):
            self.assertNotRegex(heading,r'v3\.\d+')
        self.assertIn('docs/CHANGELOG.md',text)

if __name__=='__main__':
    unittest.main()
