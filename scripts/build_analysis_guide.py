"""Build the portable HTML guide from the canonical Markdown; no extra dependencies.

Run: python3 scripts/build_analysis_guide.py [--check]
"""
import argparse
import html
from pathlib import Path
import re
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/LISTING_ANALYSIS_PROCESS.md'
TARGET = ROOT / 'docs/listing-analysis-guide.html'
GITHUB = 'https://github.com/rvolluru/valueai/blob/main/docs/'


def inline(value):
    # Escape source HTML first. Code/link tokens cannot accidentally be parsed as emphasis.
    tokens = []
    def token(fragment):
        tokens.append(fragment)
        return f'\x00{len(tokens) - 1}\x00'
    value = html.escape(value)
    value = re.sub(r'`([^`]+)`', lambda m: token('<code>' + m[1] + '</code>'), value)
    def link(match):
        href = html.unescape(match[2])
        if not href.startswith(('https://', 'http://', '#')):
            href = urljoin(GITHUB, href)
        if not href.startswith(('https://', 'http://', '#')):
            return match[1]
        return token(f'<a href="{html.escape(href, quote=True)}">{match[1]}</a>')
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
    value = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', value)
    for index, fragment in reversed(list(enumerate(tokens))):
        value = value.replace(f'\x00{index}\x00', fragment)
    return value


def render(markdown):
    lines = markdown.splitlines()
    output, toc = [], []
    index, section, maintenance = 0, False, False
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith('# '):
            index += 1
            continue
        if line.startswith('## '):
            if maintenance:
                output.append('</div></details>')
                maintenance = False
            if section:
                output.append('</section>')
            number, title = line[3:].split('. ', 1)
            anchor = 'section-' + number
            toc.append((anchor, number.zfill(2), title))
            output.append(f'<section id="{anchor}" aria-labelledby="heading-{number}">'
                          f'<h2 id="heading-{number}"><span class="number">{number.zfill(2)}</span>{inline(title)}</h2>')
            section = True
            index += 1
            continue
        if line.startswith('### Document maintenance'):
            output.append('<details class="source-note"><summary>About this living document</summary><div>')
            maintenance = True
            index += 1
            continue
        if line.startswith('### '):
            output.append('<h3>' + inline(line[4:]) + '</h3>')
            index += 1
            continue
        if line.startswith('```'):
            index += 1
            code = []
            while index < len(lines) and not lines[index].startswith('```'):
                code.append(lines[index])
                index += 1
            is_flow = 'Original photos' in code
            label = 'End-to-end process map' if is_flow else 'Calculation / example'
            output.append(f'<figure class="code-block {"flow" if is_flow else ""}">'
                          f'<figcaption>{label}</figcaption><pre tabindex="0" aria-label="{label}"><code>'
                          + html.escape('\n'.join(code)) + '</code></pre></figure>')
            index += 1
            continue
        if line.startswith('|'):
            rows = []
            while index < len(lines) and lines[index].startswith('|'):
                rows.append([cell.strip() for cell in lines[index].strip().strip('|').split('|')])
                index += 1
            output.append('<div class="table-scroll" role="region" tabindex="0" aria-label="Scrollable reference table"><table><thead><tr>')
            output.extend('<th scope="col">' + inline(cell) + '</th>' for cell in rows[0])
            output.append('</tr></thead><tbody>')
            for row in rows[2:]:
                output.append('<tr>' + ''.join('<td>' + inline(cell) + '</td>' for cell in row) + '</tr>')
            output.append('</tbody></table></div>')
            continue
        if line.startswith('> '):
            quote = []
            while index < len(lines) and lines[index].startswith('> '):
                quote.append(lines[index][2:])
                index += 1
            output.append('<blockquote><span class="eyebrow">Viewer disclosure</span><p>' + inline(' '.join(quote)) + '</p></blockquote>')
            continue
        if re.match(r'^(?:- |\d+\. )', line):
            ordered = bool(re.match(r'^\d+\. ', line))
            tag = 'ol' if ordered else 'ul'
            output.append('<' + tag + '>')
            while index < len(lines) and re.match(r'^(?:- |\d+\. )', lines[index]):
                item = [re.sub(r'^(?:- |\d+\. )', '', lines[index])]
                index += 1
                while index < len(lines) and lines[index].startswith('  ') and lines[index].strip():
                    item.append(lines[index].strip())
                    index += 1
                output.append('<li>' + inline(' '.join(item)) + '</li>')
            output.append('</' + tag + '>')
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r'^(?:#|```|\||>|- |\d+\. )', lines[index]):
            paragraph.append(lines[index])
            index += 1
        value = ' '.join(paragraph)
        css = ' class="status-note"' if value.startswith('**Implementation status:') else ''
        output.append(f'<p{css}>' + inline(value) + '</p>')
    if section:
        output.append('</section>')
    return '\n'.join(output), toc


STYLE = """
:root{--wine:#571921;--ink:#262321;--muted:#6e655e;--paper:#faf7f1;--line:#e3dbd1;--soft:#f0e9df;--white:#fffdf9;--green:#365c4b}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--wine);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}button,summary,a{-webkit-tap-highlight-color:transparent}a:focus-visible,button:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid #b57939;outline-offset:4px}
.skip{position:absolute;left:24px;top:-80px;background:white;padding:12px;z-index:20}.skip:focus{top:12px}.topbar{max-width:1440px;margin:auto;padding:24px 5%;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);gap:18px}
.brand{font:38px/.95 Georgia,serif;letter-spacing:.11em;color:var(--wine);text-decoration:none}.top-label,.eyebrow{font-size:11px;font-weight:650;letter-spacing:.19em;text-transform:uppercase}.top-label{color:var(--muted)}.top-actions{display:flex;gap:18px;align-items:center;font-size:13px}.print{font:inherit;border:1px solid var(--line);padding:8px 14px;background:var(--white);color:var(--wine);cursor:pointer}
.hero{max-width:1440px;margin:auto;padding:72px 5% 56px;display:grid;grid-template-columns:minmax(0,1.6fr) minmax(240px,.8fr);gap:60px;align-items:end}.hero .eyebrow{color:var(--wine)}h1{font:clamp(44px,5.5vw,78px)/1.05 Georgia,serif;font-weight:400;letter-spacing:-.045em;margin:20px 0 24px;max-width:850px}.hero p{color:var(--muted);font-size:18px;max-width:620px;margin:0}.hero-aside{padding:24px 0 4px 26px;border-left:2px solid var(--wine)}.hero-aside p{font-size:14px;margin:10px 0}.hero-aside strong{color:var(--wine)}.meta{display:flex;gap:18px;flex-wrap:wrap;margin-top:28px;color:var(--muted);font-size:12px}.badge{color:var(--green);border:1px solid #c9d7ce;padding:2px 9px;border-radius:20px}
.journey{max-width:1296px;margin:0 auto 54px;padding:28px 32px;background:var(--wine);color:#fffaf4;display:grid;grid-template-columns:repeat(4,1fr);gap:28px}.journey span{display:block;color:#d6b6b5;font-size:11px;letter-spacing:.13em;text-transform:uppercase}.journey strong{display:block;font:25px/1.3 Georgia,serif;margin:7px 0}.journey small{font-size:12px;line-height:1.5;color:#eadad5}
.layout{max-width:1440px;margin:auto;padding:0 5% 80px;display:grid;grid-template-columns:250px minmax(0,1fr);gap:60px}.sidebar{align-self:start;position:sticky;top:24px;max-height:calc(100vh - 48px);overflow:auto;padding-right:12px}.sidebar summary{cursor:pointer;font-size:12px;font-weight:650;letter-spacing:.1em;text-transform:uppercase;color:var(--wine);padding:8px 0 16px}.toc-list{list-style:none;margin:0;padding:0}.toc-list li{margin:0;border-bottom:1px solid var(--line)}.toc-list a{display:grid;grid-template-columns:26px 1fr;gap:7px;padding:10px 6px;text-decoration:none;font-size:12px;line-height:1.5;color:var(--muted)}.toc-list a span{font-size:10px;color:#9c8d80}.toc-list a:hover,.toc-list a[aria-current]{color:var(--wine);background:var(--soft)}
main{min-width:0;max-width:900px}main>p:first-child{color:var(--muted);font-size:14px}.status-note{border:1px solid #ddc7ae;border-left:3px solid #ac7645;background:#f6eee1;padding:20px 24px;font-size:14px;line-height:1.7}.source-note{font-size:13px;border-bottom:1px solid var(--line);padding:10px 0 18px;color:var(--muted)}.source-note summary{cursor:pointer;color:var(--wine)}section{padding:34px 0 24px;border-bottom:1px solid var(--line)}h2{font:35px/1.18 Georgia,serif;font-weight:400;letter-spacing:-.025em;display:grid;grid-template-columns:38px 1fr;gap:12px;margin:8px 0 26px;color:var(--wine)}.number{font:11px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:.07em;border-top:1px solid #b99d95;padding-top:9px;margin-top:5px;color:#8e625b}h3{font-size:19px;line-height:1.5;margin:30px 0 12px;font-weight:650}p{margin:0 0 19px}li{margin:8px 0;padding-left:4px}ul,ol{padding-left:23px;margin:16px 0 25px}li::marker{color:var(--wine)}strong{font-weight:650}code{font: .84em/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere;background:#eee7df;padding:2px 5px;border-radius:3px}
.table-scroll{overflow:auto;border:1px solid var(--line);margin:24px 0 30px;background:var(--white)}table{border-collapse:collapse;width:100%;min-width:460px;text-align:left;font-size:13px;line-height:1.65}th{background:var(--soft);color:var(--wine);font-size:11px;letter-spacing:.06em;text-transform:uppercase;font-weight:650}th,td{padding:14px 17px;vertical-align:top;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}td:first-child{font-weight:600}tbody tr:nth-child(even){background:#f8f4ed}td code{font-size:11px}.code-block{margin:26px 0;background:#eee8de;border:1px solid var(--line)}figcaption{font-size:10px;letter-spacing:.15em;text-transform:uppercase;padding:13px 20px;border-bottom:1px solid #dbd1c6;color:var(--muted)}pre{margin:0;padding:23px;overflow:auto;font-size:12px;line-height:1.6;tab-size:2}pre code{padding:0;background:none;border-radius:0;font-size:inherit;overflow-wrap:normal}.flow{background:#f0ebe3}.flow pre{font-size:12px;line-height:1.7}blockquote{margin:28px 0;padding:25px 28px;background:var(--soft);border-left:3px solid var(--wine)}blockquote .eyebrow{color:var(--wine)}blockquote p{font:23px/1.5 Georgia,serif;margin:12px 0 0}.footer{border-top:1px solid var(--line);padding:30px 5%;max-width:1440px;margin:auto;display:flex;justify-content:space-between;gap:20px;color:var(--muted);font-size:12px}.footer a{color:inherit}
@media(min-width:1450px){.journey{max-width:1296px}}@media(max-width:1100px){.layout{gap:32px;grid-template-columns:210px minmax(0,1fr)}.hero{gap:30px}.journey{margin-left:5%;margin-right:5%}}
@media(max-width:800px){body{font-size:16px}.topbar{padding:20px 6%}.brand{font-size:30px}.top-label{display:none}.top-actions{gap:12px;font-size:11px}.hero{padding:42px 6% 32px;grid-template-columns:1fr;gap:28px}.hero-aside{padding:8px 0 8px 18px}.hero p{font-size:16px}.meta{margin-top:20px}.journey{margin:0 6% 28px;padding:24px;grid-template-columns:1fr 1fr;gap:24px}.journey strong{font-size:22px}.layout{padding:0 6% 45px;display:block}.sidebar{position:static;max-height:none;margin-bottom:25px;padding:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.sidebar summary{padding:15px 0}.toc-list{padding-bottom:15px}.toc-list a{font-size:13px;padding:9px}.toc-list li:last-child{border:0}h2{font-size:29px;grid-template-columns:28px 1fr;gap:10px}h3{font-size:18px}section{padding-top:28px}.status-note{padding:17px}.footer{padding:24px 6%;display:block}.footer span{display:block;margin:5px 0}.flow pre{font-size:11px}pre{padding:17px}blockquote p{font-size:21px}}
@media print{@page{size:A4;margin:18mm}body{font-size:10pt;line-height:1.55;background:white;color:#222}.topbar,.sidebar,.journey,.top-actions,.skip,.footer,.hero-aside{display:none!important}.hero{display:block;padding:0 0 20px}.hero h1{font-size:34pt;max-width:none;margin:12px 0}.hero p{font-size:11pt}.hero .eyebrow{font-size:9pt}.meta{margin-top:14px}.layout{display:block;padding:0;max-width:none}main{max-width:none}.status-note{font-size:9pt;background:white}.source-note{display:none}section{padding:18px 0 10px}h2{font-size:23pt;break-after:avoid}h3{font-size:12pt;break-after:avoid}p,li{orphans:3;widows:3}table{min-width:0;font-size:8.5pt}th,td{padding:8px}tr{break-inside:avoid}thead{display:table-header-group}.table-scroll{overflow:visible}pre,.flow pre{font-size:8pt;white-space:pre-wrap;overflow:visible}blockquote{break-inside:avoid}blockquote p{font-size:13pt}a{color:inherit}code{font-size:8pt}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


def build():
    markdown = SOURCE.read_text()
    content, toc = render(markdown)
    if len(toc) != len(re.findall(r'^## ', markdown, re.M)):
        raise ValueError('Not all sections were rendered')
    navigation = ''.join(f'<li><a href="#{anchor}"><span>{number}</span>{html.escape(title)}</a></li>' for anchor, number, title in toc)
    words = len(markdown.split())
    minutes = max(1, round(words / 220))
    updated = re.search(r'^Updated ([^.]+)\.', markdown, re.M)
    if not updated:
        raise ValueError('Source must declare its updated date')
    updated_date = html.escape(updated[1])
    source_url = GITHUB + SOURCE.name
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="The complete Jouft listing analysis process: from original photos to identification, pricing, AI previews and publication.">
<title>Jouft · The listing analysis guide</title><style>{STYLE}</style></head><body>
<a class="skip" href="#guide">Skip to the guide</a>
<header class="topbar"><a class="brand" href="#top" aria-label="Jouft guide, top">JOUFT</a><span class="top-label">Product &amp; platform documentation</span><div class="top-actions"><a href="{source_url}">Source &amp; history</a><button class="print" type="button" onclick="window.print()">Print / Save PDF</button></div></header>
<div id="top" class="hero"><div><span class="eyebrow">The complete process · Functional guide</span><h1>Listing analysis,<br>from photo to publish.</h1><p>A practical guide to the evidence, models and decisions behind every Jouft listing.</p><div class="meta"><span>Updated {updated_date}</span><span>{minutes}-minute read</span><span class="badge">Versioned living document</span></div></div><aside class="hero-aside" aria-label="Core principle"><span class="eyebrow">At the heart of the process</span><p>Original photos are the evidence.<br>AI helps identify, value and present.<br><strong>The owner decides what goes live.</strong></p></aside></div>
<div class="journey" aria-label="Process overview"><div><span>01 · Evidence</span><strong>Capture &amp; check</strong><small>Original photos, coverage and item facts.</small></div><div><span>02 · Understand</span><strong>Identify &amp; value</strong><small>Product evidence and condition-specific pricing.</small></div><div><span>03 · Present</span><strong>Preview &amp; refine</strong><small>Optional styling and photo cleanup.</small></div><div><span>04 · Owner control</span><strong>Review &amp; publish</strong><small>Confirm details and choose public images.</small></div></div>
<div class="layout"><nav class="sidebar" aria-label="Table of contents"><details id="contents" open><summary>On this page · {len(toc)} sections</summary><ul class="toc-list">{navigation}</ul></details></nav><main id="guide">{content}</main></div>
<footer class="footer"><span>JOUFT · Listing analysis guide</span><span>Generated from the <a href="{source_url}">versioned process document</a>. No external fonts, scripts or tracking.</span></footer>
<script>
const contents=document.getElementById('contents');const mobile=window.matchMedia('(max-width:800px)');
const adapt=()=>{{contents.open=!mobile.matches}};adapt();mobile.addEventListener('change',adapt);
document.querySelectorAll('.toc-list a').forEach(a=>a.addEventListener('click',()=>{{if(mobile.matches)contents.open=false}}));
if('IntersectionObserver' in window){{const links=[...document.querySelectorAll('.toc-list a')];const observer=new IntersectionObserver(entries=>{{entries.forEach(entry=>{{if(entry.isIntersecting){{links.forEach(a=>a.removeAttribute('aria-current'));const link=links.find(a=>a.hash==='#'+entry.target.id);if(link)link.setAttribute('aria-current','location')}}}})}},{{rootMargin:'-10% 0px -65% 0px'}});document.querySelectorAll('main section').forEach(section=>observer.observe(section))}}
</script></body></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if generated HTML is out of date')
    args = parser.parse_args()
    result = build()
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != result:
            raise SystemExit('HTML guide is stale. Run python3 scripts/build_analysis_guide.py')
        print('HTML guide matches the canonical Markdown.')
    else:
        TARGET.write_text(result)
        print(f'Built {TARGET.relative_to(ROOT)} ({len(result):,} characters)')
