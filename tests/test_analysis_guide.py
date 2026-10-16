import importlib.util
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('analysis_guide', ROOT / 'scripts/build_analysis_guide.py')
guide = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guide)


def test_generated_guide_matches_source_and_has_all_navigation_targets():
    result = guide.build()
    assert result == guide.TARGET.read_text()
    class Inspect(HTMLParser):
        ids = []
        anchors = []
        external_assets = []
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if values.get('id'):
                self.ids.append(values['id'])
            if tag == 'a' and values.get('href', '').startswith('#'):
                self.anchors.append(values['href'][1:])
            if tag in {'script', 'img', 'iframe', 'link'} and (values.get('src') or values.get('href')):
                self.external_assets.append(values)
    parsed = Inspect()
    parsed.feed(result)
    assert len(parsed.ids) == len(set(parsed.ids))
    assert all(target in parsed.ids for target in parsed.anchors)
    assert all('section-' + str(number) in parsed.ids for number in range(1, 19))
    assert not parsed.external_assets


def test_inline_rendering_escapes_html_and_preserves_code():
    result = guide.inline('**Evidence** `<script>` [Instructions](../AGENTS.md)')
    assert '<strong>Evidence</strong>' in result
    assert '<code>&lt;script&gt;</code>' in result
    assert 'href="https://github.com/rvolluru/valueai/blob/main/AGENTS.md"' in result
    assert '<script>' not in result
    assert 'javascript:' not in guide.inline('[Unsafe](javascript:alert)')


def test_markdown_tables_lists_flow_and_disclosure_are_rendered():
    result = guide.build()
    assert '<thead>' in result and '<th scope="col">' in result
    assert '<ol>' in result and '<ul>' in result
    assert 'End-to-end process map' in result
    assert 'AI-generated styling preview.' in result
    assert '<blockquote>' in result
    assert '\x00' not in result
