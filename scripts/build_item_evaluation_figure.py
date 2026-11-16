"""Generate a source-backed, patent-style SVG of the implemented evaluation flow."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'output/diagrams/item-evaluation.svg'
parts = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="2310" viewBox="0 0 1600 2310" role="img" aria-labelledby="title desc">
<title id="title">Jouft implemented item evaluation process</title>
<desc id="desc">Original-photo coverage and user facts lead to a private analysis job. Qualified analysis can be reused, otherwise saved identity or Gemini identification feeds OpenAI pricing. Validated condition-aligned pricing is saved, or missing value is routed for manual review. Optional mannequin and hero cleanup run independently. Publication requires separate owner approval.</desc>
<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="black"/></marker></defs>
<rect width="1600" height="2310" fill="white"/>
<style>text{font-family:Arial,Helvetica,sans-serif;fill:#000;font-size:23px} .small{font-size:19px}.caption{font-size:31px;font-weight:bold}.note{font-size:20px}.number{font-size:21px}rect,polygon{stroke:#000;stroke-width:2.3} .optional{stroke-dasharray:10 7}.edge{fill:none;stroke:#000;stroke-width:2.3;marker-end:url(#arrow)}</style>''']


def text(x, y, lines, cls='', anchor='middle'):
    if isinstance(lines, str):
        lines = lines.split('\n')
    for i, line in enumerate(lines):
        parts.append(f'<text x="{x}" y="{y+i*29}" text-anchor="{anchor}" class="{cls}">{escape(line)}</text>')


def box(x, y, w, h, lines, number=None, dashed=False):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="white" class="{"optional" if dashed else ""}"/>')
    n = len(lines.split('\n'))
    text(x+w/2, y+h/2-(n-1)*14.5+8, lines)
    if number:
        text(x+w+12, y+22, str(number), 'number', 'start')


def diamond(x, y, w, h, label, number):
    parts.append(f'<polygon points="{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}" fill="white"/>')
    text(x+w/2, y+h/2-6, label)
    text(x+w+12, y+25, str(number), 'number', 'start')


def arrow(points, label=None, at=None, dashed=False):
    parts.append(f'<polyline points="{points}" class="edge" {"stroke-dasharray='9 6'" if dashed else ""}/>')
    if label:
        text(*at, label, 'small')


text(800, 48, 'JOUFT   IMPLEMENTED ITEM EVALUATION', 'caption')
text(800, 82, 'Functional process as inspected October 30, 2026', 'small')
box(420, 125, 560, 85, 'Receive original photos\n(up to six) and listing context', 102)
arrow('700,210 700,245')
box(420, 245, 560, 85, 'Gemini checks photo roles,\ncategory and required coverage', 104)
arrow('700,330 700,365')
diamond(470, 365, 460, 130, 'Required evidence\ncomplete?', 106)
box(35, 380, 305, 105, 'Request missing views\nor corrected photos', 108)
arrow('470,430 340,430', 'No', (394, 414))
arrow('185,380 185,165 420,165')
arrow('700,495 700,540', 'Yes', (735, 521))
box(420, 540, 560, 95, 'Collect / validate category, condition,\nsize and optional description', 110)
arrow('700,635 700,670')
box(420, 670, 560, 90, 'Obtain explicit confirmation\nto create and analyze a private draft', 112)
arrow('700,760 700,795')
box(420, 795, 560, 95, 'Save job and freeze original evidence;\nqueue worker execution', 114)
arrow('700,890 700,930')
diamond(470, 930, 460, 140, 'Qualified complete\nanalysis reusable?', 116)
box(35, 950, 305, 115, 'Reuse qualified evidence\nand apply current\ncondition selection', 118)
arrow('470,1000 340,1000', 'Yes', (395, 985))
arrow('185,1065 15,1065 15,1990 420,1990')
arrow('700,1070 700,1110', 'No / refresh', (790, 1098))
box(420, 1110, 560, 120, 'Reuse eligible saved identity, OR\nidentify from originals with Gemini\n(label / OCR recovery when needed)', 120)
arrow('700,1230 700,1270')
box(420, 1270, 560, 120, 'Assigned OpenAI pricing model researches\napproved sources using identity and facts;\nreturns comparables and condition estimates', 122)
arrow('700,1390 700,1430')
box(420, 1430, 560, 115, 'Validate source and comparable evidence;\nselect the current condition-aligned price\n(applicable repair / condition retry)', 124)
arrow('700,1545 700,1590')
diamond(470, 1590, 460, 140, 'Valid positive\nvaluation available?', 126)
box(35, 1605, 305, 155, 'No valid value:\nsave review requirement;\ncreate admin incident\nand attempt email alert', 128)
arrow('470,1660 340,1660', 'No', (395, 1645))
arrow('185,1760 185,1990 420,1990')
arrow('700,1730 700,1805', 'Yes', (738, 1765))
box(420, 1805, 560, 115, 'Save identity, evidence and selected value,\nrange / confidence where available;\npreserve unrelated listing edits', 130)
arrow('700,1920 700,1950')
box(420, 1950, 560, 105, 'Private review state saved\nMissing value: admin pricing review required\nNo automatic publication', 132)
arrow('700,2055 700,2090')
box(420, 2090, 560, 100, 'Owner reviews facts and image choices;\npublish only after separate approval\nand backend prerequisites pass', 134)

# Presentation work forks from the frozen evidence, not from pricing output.
arrow('980,842 1150,842 1150,945', dashed=True)
text(1290, 805, 'INDEPENDENT PRESENTATION BRANCHES', 'small')
box(1070, 945, 440, 205, 'Mannequin preview (when applicable)\nPlan from original photos\nGenerate with Gemini\nReview coverage / fidelity\nOwner decides inclusion', 136, True)
arrow('1150,842 1565,842 1565,1210 1510,1210', dashed=True)
box(1070, 1180, 440, 170, 'Hero background cleanup\nPhotoroom mask for hero only\nComposite original pixels over white\nFailure: retain original', 138, True)
text(1290, 1410, 'Each branch saves independently.\nOptional images may finish later.\nNeither branch sets the valuation.\nGenerated images are not price evidence.', 'note')
parts.append('<rect x="1070" y="1600" width="440" height="325" fill="white" class="optional"/>')
text(1290, 1640, 'IMPLEMENTATION NOTES', 'small')
text(1290, 1685, 'Reuse requires matching evidence\nand current pricing-policy qualification.\n\nIdentity has its own reuse rules.\n\nNo discrete value-band classifier\nor universal authenticity-pass gate\nis implied by this figure.', 'note')
text(800, 2247, 'FIG. 1   CURRENT ITEM EVALUATION FLOW', 'caption')
text(800, 2284, 'Reference numerals identify this figure only; they do not reuse PPA component meanings.', 'small')
parts.append('</svg>')
TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text('\n'.join(parts))
print(TARGET)
