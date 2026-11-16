"""Render the implemented hybrid pricing path as an editable patent-style SVG."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/diagrams/item-pricing.svg'
svg = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1900" height="3250" viewBox="0 0 1900 3250" role="img" aria-labelledby="title desc">
<title id="title">How Jouft determines an item price</title><desc id="desc">The implemented hybrid pricing path checks qualified reuse, resolves identity and a persisted pricing model, researches approved websites, validates comparable evidence, selects a condition-aligned estimate, and saves a value or requests manual pricing review. Presentation images do not set the price.</desc>
<defs><marker id="a" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z"/></marker></defs>
<rect width="1900" height="3250" fill="white"/>
<style>text{font-family:Arial,Helvetica,sans-serif;fill:black;font-size:24px}.small{font-size:21px}.title{font-size:35px;font-weight:bold}.heading{font-size:23px;font-weight:bold}rect,polygon{stroke:black;stroke-width:2.5}.edge{stroke:black;stroke-width:2.5;fill:none;marker-end:url(#a)}.optional{stroke-dasharray:10 7}</style>''']


def txt(x, y, value, cls='', anchor='middle'):
    for i, line in enumerate(value.split('\n')):
        svg.append(f'<text x="{x}" y="{y+i*31}" text-anchor="{anchor}" class="{cls}">{escape(line)}</text>')


def box(x, y, w, h, value, n=None, dashed=False):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="white" class="{"optional" if dashed else ""}"/>')
    txt(x+w/2, y+h/2-(len(value.split('\n'))-1)*15.5+8, value)
    if n:
        txt(x+w+10, y+25, str(n), 'small', 'start')


def decision(y, value, n):
    svg.append(f'<polygon points="870,{y} 1210,{y+80} 870,{y+160} 530,{y+80}" fill="white"/>')
    txt(870, y+72, value)
    txt(1220, y+28, str(n), 'small', 'start')


def edge(points, label=None, xy=None):
    svg.append(f'<polyline points="{points}" class="edge"/>')
    if label:
        txt(*xy, label, 'small')


def panel(y, h, title, body):
    svg.append(f'<rect x="1370" y="{y}" width="480" height="{h}" fill="white" class="optional"/>')
    txt(1610, y+38, title, 'heading')
    txt(1610, y+84, body, 'small')


txt(950, 50, 'JOUFT   HOW ITEM PRICING IS DETERMINED', 'title')
txt(950, 87, 'Implemented hybrid pricing path • inspected October 30, 2026', 'small')
box(460, 130, 820, 120, 'Inputs: original-photo evidence, product context,\nuser category / condition / size / description,\nlisting ID, owner and pricing-refresh request', 202)
edge('870,250 870,285')
decision(285, 'Qualified full analysis\ncan be reused?', 204)
box(40, 310, 355, 150, 'Reuse qualified analysis;\nreselect current condition\nand preserve pricing-model\nprovenance', 206)
edge('530,365 395,365', 'Yes', (452, 347))
edge('217,460 20,460 20,2840 460,2840')
edge('870,445 870,490', 'No / explicit refresh', (1025, 475))
box(460, 490, 820, 125, 'Resolve product identity:\nreuse eligible identity for this listing and owner,\nor identify from original evidence with Gemini', 208)
edge('870,615 870,650')
box(460, 650, 820, 125, 'Resolve and persist the assigned OpenAI pricing model\nExisting cohort: GPT-5; new fresh cohort: configured Sol\nRetries / repairs retain that listing assignment', 210)
edge('870,775 870,810')
box(460, 810, 820, 130, 'Send structured identity and current facts to pricing\nModel researches approved websites with web search\nPricing-specific request contains no image parts', 212)
edge('870,940 870,975')
box(460, 975, 820, 125, 'Model returns comparable records, resale estimate,\ncondition-specific estimates, range / confidence,\nrationale, references and separate retail reference', 214)
edge('870,1100 870,1135')
box(460, 1135, 820, 155, 'Server validates comparable evidence:\napproved source / USD positive price / same brand /\ncompatible product family / supported source identity;\nrelated items need similarity and adjustment explanations', 216)
edge('870,1290 870,1325')
decision(1325, 'Resale evidence policy\nqualified?', 218)
edge('530,1405 217,1405 217,2500 395,2500', 'No', (430, 1386))
edge('870,1485 870,1530', 'Yes', (908, 1514))
box(460, 1530, 820, 130, 'Check the requested condition exactly:\nNew With Tags, New and Like New are distinct\nNew must not inherit a tags / box / full-set premium', 220)
edge('870,1660 870,1695')
decision(1695, 'New has no priced New row,\nbut a usable Like New row?', 222)
box(1390, 1700, 440, 160, 'One pricing-only New inference\nSame identity and assigned model\nNo fixed percentage uplift\nConfidence capped at 20%', 224)
edge('1210,1775 1390,1775', 'Yes', (1305, 1758))
edge('1610,1860 1610,1875 870,1875 870,1890')
edge('870,1855 870,1890', 'No', (907, 1880))
box(460, 1890, 820, 130, 'Select the first eligible exact-condition value:\n1. Positive primary estimate matching user condition\n2. Otherwise, positive breakdown row for that condition', 226)
edge('870,2020 870,2060')
decision(2060, 'Recognized brand and\nvalid positive value?', 228)
edge('530,2140 217,2140 217,2500 395,2500', 'No', (430, 2120))
edge('870,2220 870,2260', 'Yes', (908, 2246))
box(460, 2260, 820, 135, 'Normalize and save selected valuation:\nUSD estimate rounded to cents; range where available;\nconfidence clamped to 0–1; basis, condition alignment,\nretail reference and inference provenance', 230)
edge('870,2395 870,2430')
box(460, 2430, 820, 130, 'Merge pricing into the identified product profile\nPricing cannot replace persisted brand/model identity\nSave result independently of presentation-image branches', 232)
box(40, 2400, 355, 205, 'No usable valuation:\ndo not restore an old price\nSave pending pricing review\nCreate admin incident\nAttempt admin email alert\nBlock publication until resolved', 234)
edge('217,2605 217,2840 460,2840')
edge('870,2560 870,2630')
box(460, 2630, 820, 135, 'Persist internal evaluation and private review state\nValue is an estimate, not a guaranteed sale price\nSeparate owner review and approval control publication', 236)
edge('870,2765 870,2805')
box(460, 2805, 820, 105, 'Saved evaluation / manual-review outcome\nNo automatic publication or trade request', 238)

panel(140, 325, 'REUSE IS EVIDENCE-BOUND', 'Full original-photo content matches;\ncondition / category / brand compatible;\ncurrent evidence-policy qualification;\nusable identity and condition price.\n\nRefresh and model-cohort rules apply.\nIdentity-only reuse does not copy\na previous valuation.');
panel(505, 380, 'WHAT THE MODEL IS ASKED TO VALUE', 'Patient peer-to-peer resale / trade\nvalue over roughly 30–60 days.\nCurrent user condition is authoritative.\nDo not price by size or season.\nSeparate original MSRP from markdowns.\nResale evidence is required.\nNWT apparel guidance is not an\nunsupported MSRP fallback.\nNo universal luxury retail-price cap.');
panel(925, 345, 'SOURCE ROLES', 'Resale: The RealReal, Poshmark,\nVestiaire Collective, Rebag, Depop,\nVinted and eBay; approved regions.\nOfficial registered brand website:\nidentity / original retail, not resale.\n\nSearch restrictions + server validation.\nNo invented official domains.');
panel(1310, 325, 'EVIDENCE VS. PRICE VERIFICATION', 'Accepted comparable URLs are deduped.\nPrimary resale references must point\nto accepted comparable evidence.\nUnsupported exact claims can become\nrelated with required explanations.\nMissing official retail clears retail only.\nFailed resale policy clears pricing;\nno fallback restores rejected value.');
panel(2030, 335, 'NO FIXED PRICING FORMULA', 'The active path uses model estimation\nplus deterministic acceptance rules.\nIt does not compute a universal\nweighted mean of comparable prices.\nModel confidence is not a calibrated\nprobability or an admission threshold.\nAn allowed source alone does not prove\nthe price or sale was verified.');
panel(2410, 330, 'LEGACY / OPTIONAL PATHS', 'Retail-factor fallback exists only for\nprofiles without a pricing-policy marker.\nCurrent qualified profiles do not use it.\nSeparate crawler-comparable fallback\nis gated and disabled in the recorded\nproduction configuration.\nControlled per-site research is also\nnot the active search path.');
panel(2780, 230, 'NOT PRICING INPUTS', 'Mannequin styling previews and\nPhotoroom hero display variants\ndo not replace original evidence.\nNo discrete marketplace value band\nis assigned by this pricing flow.');
txt(950, 3100, 'FIG. 2   IMPLEMENTED PRICING DECISIONS AND EVIDENCE CHECKS', 'title')
txt(950, 3142, 'Internal evaluation process; the figure does not specify end-user monetary-value visibility.', 'small')
txt(950, 3175, 'Numbers identify this figure only. Dashed panels explain policy or optional behavior; they are not sequential steps.', 'small')
txt(950, 3208, 'Sources: gpt_item_profile.py · pricing_evidence.py · pricing_models.py · main.py · LISTING_ANALYSIS_PROCESS.md', 'small')
svg.append('</svg>')
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text('\n'.join(svg))
print(OUT)
