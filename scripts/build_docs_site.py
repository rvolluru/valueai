"""Build standalone architecture guide and documentation home. Run with --check in CI."""
import argparse
import html
from pathlib import Path
import re
import subprocess

from build_analysis_guide import STYLE, render

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
GITHUB = 'https://github.com/rvolluru/valueai/blob/main/'
EXTRA = '''
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin:28px 0}
.card{border:1px solid var(--line);background:var(--white);padding:26px;text-decoration:none;display:block}
.card:hover{border-color:var(--wine)}.card h3{font:28px/1.2 Georgia,serif;margin:12px 0;color:var(--wine)}
.card p{font-size:14px;color:var(--muted);margin:0}.card small{overflow-wrap:anywhere;color:var(--muted);font-size:11px}
.home{max-width:1296px;margin:auto;padding:0 5% 70px}.home h2{display:block}.home input{width:100%;padding:16px;border:1px solid var(--line);background:var(--white);font:inherit;color:var(--ink)}
.map{background:var(--soft);border:1px solid var(--line);padding:26px;margin:25px 0}.map-row{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.node{padding:14px 18px;border:1px solid var(--line);background:var(--white);text-align:center;font-size:13px;flex:1;min-width:150px}.node strong{display:block;color:var(--wine)}
.connector{text-align:center;color:var(--muted);font-size:12px;padding:10px}.map figcaption{padding:0 0 16px;margin-bottom:20px}.featured{background:var(--wine);color:white}.featured h3,.featured p,.featured small{color:white}
[hidden]{display:none!important}.home section{border:0}.home .number{display:none}
.hero>*,.card{min-width:0}.card h3{overflow-wrap:anywhere}
@media(max-width:700px){.cards{grid-template-columns:minmax(0,1fr)}.map{padding:16px}.node{min-width:120px}.topbar{flex-wrap:wrap}.top-actions{flex-wrap:wrap}.hero{grid-template-columns:minmax(0,1fr)}.hero h1{overflow-wrap:anywhere}.home{width:100%;min-width:0}}
@media print{.cards{display:block}.card{break-inside:avoid;margin-bottom:12px}.home input{display:none}.map{break-inside:avoid}}
'''


def page(title, body):
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Jouft engineering documentation: architecture, services, workflows and operations.">
<title>Jouft · {html.escape(title)}</title><style>{STYLE}{EXTRA}</style></head><body>
<a class="skip" href="#guide">Skip to content</a>
<header class="topbar"><a class="brand" href="index.html">JOUFT</a><span class="top-label">Product &amp; platform documentation</span>
<div class="top-actions"><a href="index.html">Docs home</a><button class="print" onclick="window.print()">Print / Save PDF</button></div></header>
{body}<footer class="footer"><span>JOUFT · Engineering library</span><span>Generated from versioned repository sources. No external fonts, scripts or tracking.</span></footer>
</body></html>'''


def architecture():
    markdown = (DOCS / 'SYSTEM_ARCHITECTURE.md').read_text()
    # A native HTML map renders offline; retain canonical Mermaid in Markdown.
    markdown, count = re.subn(r'```mermaid\n.*?\n```', 'ARCHITECTURE_MAP', markdown, flags=re.S)
    if count != 1:
        raise ValueError('Expected one canonical architecture diagram')
    content, toc = render(markdown)
    for name in ('index.html', 'system-architecture-guide.html', 'listing-analysis-guide.html'):
        content = content.replace(f'href="{GITHUB}docs/{name}"', f'href="{name}"')
    diagram = '''<figure class="map" aria-label="System architecture map"><figcaption>System map · connections and responsibilities</figcaption>
<div class="map-row"><div class="node"><strong>React web</strong>Browser client</div><div class="node"><strong>Expo mobile</strong>iOS &amp; Android</div><div class="node"><strong>Clerk</strong>Client sessions / API verification</div></div>
<div class="connector">Clients → HTTPS / application load balancer → API</div>
<div class="map-row"><div class="node"><strong>FastAPI · ECS Fargate</strong>Web assets, application tools, ownership &amp; approvals</div></div>
<div class="connector">API ↔ PostgreSQL / S3 · API → SQS → worker</div>
<div class="map-row"><div class="node"><strong>RDS PostgreSQL</strong>Durable business &amp; job state</div><div class="node"><strong>S3</strong>Originals &amp; presentation assets</div><div class="node"><strong>SQS + DLQ</strong>Analysis delivery &amp; redrive</div></div>
<div class="connector">Worker ↔ PostgreSQL / S3 · API and worker → provider calls / logs</div>
<div class="map-row"><div class="node"><strong>Analysis worker · ECS</strong>Pricing, mannequin &amp; hero cleanup</div><div class="node"><strong>OpenAI / Gemini / Photoroom</strong>AI and image services</div></div>
<div class="connector">API → payments, shipping, support, addresses &amp; notifications · services → CloudWatch</div>
<div class="map-row"><div class="node"><strong>Stripe · Shippo · Plain · Places</strong>Transactional integrations</div><div class="node"><strong>SES / SMTP · Expo Push</strong>Outbound notifications</div></div></figure>'''
    content = content.replace('<p>ARCHITECTURE_MAP</p>', diagram)
    nav = ''.join(f'<li><a href="#{a}"><span>{n}</span>{html.escape(t)}</a></li>' for a, n, t in toc)
    date = re.search(r'^Updated: (.+)\.$', markdown, re.M)[1]
    return page('System architecture', f'''
<div class="hero"><div><span class="eyebrow">Architecture · Services · Trust boundaries</span><h1>One platform.<br>A connected system.</h1><p>How Jouft’s clients, application services, data stores and third-party providers work together.</p><div class="meta"><span>Updated {html.escape(date)}</span><span class="badge">Source-backed reference</span></div></div>
<aside class="hero-aside"><span class="eyebrow">Read the boundaries</span><p>Implemented is not always enabled.<br>Configured is not always healthy.<br><strong>Deployment evidence is labeled separately.</strong></p><a href="{GITHUB}docs/SYSTEM_ARCHITECTURE.md">Markdown source &amp; history</a></aside></div>
<div class="journey"><div><span>01 · Experience</span><strong>Web &amp; mobile</strong><small>Shared contracts, native and browser interfaces.</small></div><div><span>02 · Control</span><strong>API &amp; tools</strong><small>Authentication, validation and explicit approval.</small></div><div><span>03 · Execution</span><strong>Jobs &amp; evidence</strong><small>Durable state and independently saved results.</small></div><div><span>04 · Ecosystem</span><strong>Provider services</strong><small>Purpose, configuration and data boundaries.</small></div></div>
<div class="layout"><nav class="sidebar" aria-label="Table of contents"><details open><summary>Explore · {len(toc)} sections</summary><ul class="toc-list">{nav}</ul></details></nav><main id="guide">{content}</main></div>''')


def document_paths():
    tracked = subprocess.check_output(['git', 'ls-files', '*.md'], cwd=ROOT, text=True).splitlines()
    # Include the architecture source before its first commit; never crawl ignored artifacts.
    return sorted(set(tracked) | {'docs/SYSTEM_ARCHITECTURE.md'})


def home():
    groups = {'Platform & product': [], 'AI & listing analysis': [], 'Operations & releases': [], 'Repository & development': []}
    for path in document_paths():
        source = ROOT / path
        if not source.is_file():
            continue
        markdown = source.read_text()
        title = next((line.lstrip('# ').strip() for line in markdown.splitlines() if line.startswith('# ')), source.stem)
        if any(key in path for key in ('ANALYSIS', 'analysis-', 'AI_MODEL', 'LABELING', 'CHATBOT')):
            group = 'AI & listing analysis'
        elif any(key in path for key in ('DEPLOY', 'MIGRATION', 'STAGING', 'RELEASE', 'apps/mobile/README')):
            group = 'Operations & releases'
        elif path.startswith('docs/'):
            group = 'Platform & product'
        else:
            group = 'Repository & development'
        groups[group].append((path, title))
    sections = []
    for group, entries in groups.items():
        cards = ''.join(f'<a class="card document" href="{GITHUB}{html.escape(path, quote=True)}"><small>{html.escape(path)}</small><h3>{html.escape(title)}</h3><p>Read the versioned Markdown reference ↗</p></a>' for path, title in entries)
        sections.append(f'<section class="category"><h2>{group}</h2><div class="cards">{cards}</div></section>')
    return page('Documentation', '''
<div class="hero"><div><span class="eyebrow">The Jouft documentation library</span><h1>Understand the system.<br>Build with confidence.</h1><p>Your starting point for platform architecture, listing intelligence, API contracts and release operations.</p></div><aside class="hero-aside"><span class="eyebrow">A living library</span><p>Guides open as portable HTML.<br>Reference documents link to GitHub.<br><strong>Check each document’s status and date.</strong></p></aside></div>
<main id="guide" class="home"><div class="cards"><a class="card featured" href="system-architecture-guide.html"><small>START HERE · PLATFORM</small><h3>System architecture</h3><p>Components, request flows, infrastructure and the complete third-party service inventory.</p></a><a class="card featured" href="listing-analysis-guide.html"><small>DEEP DIVE · FUNCTIONAL PROCESS</small><h3>The listing analysis guide</h3><p>From original-photo evidence to identity, pricing, image presentation and publication.</p></a></div>
<label for="search" class="eyebrow">Find a reference</label><input id="search" type="search" placeholder="Search titles or file paths…" autocomplete="off"><p id="count" role="status" aria-live="polite"></p>
''' + ''.join(sections) + '''<noscript><p>All documents are listed above. Search requires JavaScript.</p></noscript></main>
<script>const input=document.getElementById('search');const cards=[...document.querySelectorAll('.document')];function filter(){const q=input.value.toLowerCase();let n=0;cards.forEach(c=>{c.hidden=!c.textContent.toLowerCase().includes(q);if(!c.hidden)n++});document.querySelectorAll('.category').forEach(s=>{s.hidden=![...s.querySelectorAll('.document')].some(c=>!c.hidden)});document.getElementById('count').textContent=n+' documents';}input.addEventListener('input',filter);filter();</script>''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, content in {'system-architecture-guide.html': architecture(), 'index.html': home()}.items():
        target = DOCS / name
        if args.check:
            if not target.exists() or target.read_text() != content:
                raise SystemExit(f'{name} is stale; run python3 scripts/build_docs_site.py')
            print(f'{name} is synchronized')
        else:
            target.write_text(content)
            print(f'Built docs/{name}')
