import asyncio
import os
import re
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

import httpx
from PIL import Image as PILImage
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette ──────────────────────────────────────────────────────────────────
CREAM = HexColor('#FFF8E7')
TEAL = HexColor('#1A535C')
TEAL_ACCENT = HexColor('#4ECDC4')
YELLOW_BOX = HexColor('#FFFDE0')
YELLOW_BORDER = HexColor('#E0C800')
BODY_COLOR = HexColor('#1A1A1A')
FOOTER_COLOR = HexColor('#888888')

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm


# ── Styles ───────────────────────────────────────────────────────────────────
def _build_styles() -> Dict[str, ParagraphStyle]:
    return {
        'title': ParagraphStyle(
            'Title_', fontName='Helvetica-Bold', fontSize=28, textColor=TEAL,
            alignment=TA_CENTER, spaceAfter=16, leading=36,
        ),
        'subtitle': ParagraphStyle(
            'Sub_', fontName='Helvetica', fontSize=13, textColor=BODY_COLOR,
            alignment=TA_CENTER, spaceAfter=8,
        ),
        'chapter': ParagraphStyle(
            'Ch_', fontName='Helvetica-Bold', fontSize=17, textColor=TEAL,
            spaceBefore=18, spaceAfter=6, leading=22,
        ),
        'body': ParagraphStyle(
            'Body_', fontName='Helvetica', fontSize=11, textColor=BODY_COLOR,
            spaceAfter=8, leading=16, alignment=TA_JUSTIFY,
        ),
        'bullet': ParagraphStyle(
            'Bullet_', fontName='Helvetica', fontSize=11, textColor=BODY_COLOR,
            spaceAfter=5, leading=16, leftIndent=24, firstLineIndent=-12,
        ),
        'example_label': ParagraphStyle(
            'ExL_', fontName='Helvetica-Bold', fontSize=11, textColor=TEAL, spaceAfter=4,
        ),
        'example_body': ParagraphStyle(
            'ExB_', fontName='Helvetica-Oblique', fontSize=11,
            textColor=HexColor('#3A3A3A'), leading=16,
        ),
        'intro': ParagraphStyle(
            'Intro_', fontName='Helvetica', fontSize=12, textColor=BODY_COLOR,
            spaceAfter=12, leading=18, alignment=TA_JUSTIFY,
        ),
        'takeaway': ParagraphStyle(
            'TK_', fontName='Helvetica', fontSize=12, textColor=BODY_COLOR,
            spaceAfter=8, leading=18, leftIndent=20,
        ),
    }


# ── Page background + footer ─────────────────────────────────────────────────
def _on_page(canvas_obj, doc) -> None:
    canvas_obj.saveState()

    # Cream background
    canvas_obj.setFillColor(CREAM)
    canvas_obj.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    page_num = canvas_obj.getPageNumber()
    if page_num > 1:
        # Top accent line
        canvas_obj.setStrokeColor(TEAL_ACCENT)
        canvas_obj.setLineWidth(2)
        canvas_obj.line(MARGIN, PAGE_H - 18 * mm, PAGE_W - MARGIN, PAGE_H - 18 * mm)

        # Footer
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.setFillColor(FOOTER_COLOR)
        title: str = getattr(doc, '_video_title', '')
        if len(title) > 65:
            title = title[:62] + '...'
        canvas_obj.drawString(MARGIN, 14 * mm, title)
        canvas_obj.drawRightString(PAGE_W - MARGIN, 14 * mm, f'Page {page_num - 1}')

    canvas_obj.restoreState()


# ── Markdown → ReportLab helpers ─────────────────────────────────────────────
def _clean_md(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.+?)`', r'<font name="Courier">\1</font>', text)
    return text


def _add_example_box(flowables: list, text: str, styles: dict, usable_w: float) -> None:
    rows = [
        [Paragraph('💡 Real Example', styles['example_label'])],
        [Paragraph(text or '(See the video for this example)', styles['example_body'])],
    ]
    t = Table(rows, colWidths=[usable_w - 24])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), YELLOW_BOX),
        ('BOX', (0, 0), (-1, -1), 1.2, YELLOW_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    flowables.append(Spacer(1, 6))
    flowables.append(t)
    flowables.append(Spacer(1, 6))


def _parse_section(text: str, styles: dict, usable_w: float) -> List:
    """Convert LLM markdown output to a list of ReportLab flowables."""
    flowables: list = []
    lines = text.strip().split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Headings
        if line.startswith('## ') or line.startswith('### '):
            prefix = 3 if line.startswith('## ') else 4
            flowables.append(Paragraph(_clean_md(line[prefix:]), styles['chapter']))
            flowables.append(HRFlowable(width='100%', thickness=1.5, color=TEAL_ACCENT, spaceAfter=4))

        elif line.startswith('# '):
            flowables.append(Paragraph(_clean_md(line[2:]), styles['chapter']))
            flowables.append(HRFlowable(width='100%', thickness=1.5, color=TEAL_ACCENT, spaceAfter=4))

        # Bullets
        elif re.match(r'^[-*•▸▪]\s', line):
            bullet_text = _clean_md(re.sub(r'^[-*•▸▪]\s+', '', line))
            flowables.append(Paragraph(f'▪  {bullet_text}', styles['bullet']))

        # Example box triggered by "Real Example" line
        elif re.search(r'real[\s_-]?example', line, re.IGNORECASE) or line.lower().startswith('example:'):
            example_lines: List[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if nxt.startswith('#') or (not nxt and example_lines):
                    break
                if nxt and not re.search(r'real[\s_-]?example', nxt, re.IGNORECASE):
                    example_lines.append(_clean_md(nxt))
                i += 1
            _add_example_box(flowables, ' '.join(example_lines), styles, usable_w)
            continue

        # Bold-wrapped example trigger: **Real Example:** or **💡 ...**
        elif re.search(r'\*\*(real|💡)[^*]*\*\*', line, re.IGNORECASE):
            rest = re.sub(r'\*\*(real|💡)[^*]*\*\*:?\s*', '', line, flags=re.IGNORECASE).strip()
            example_lines = [rest] if rest else []
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt or nxt.startswith('#'):
                    break
                example_lines.append(_clean_md(nxt))
                i += 1
            _add_example_box(flowables, ' '.join(example_lines), styles, usable_w)
            continue

        # Body text
        else:
            clean = _clean_md(line)
            if clean:
                flowables.append(Paragraph(clean, styles['body']))

        i += 1

    return flowables


# ── Synchronous PDF build (run in executor) ───────────────────────────────────
def _build_pdf_sync(
    output_path: str,
    title: str,
    thumbnail_data: Optional[BytesIO],
    assembled: dict,
) -> None:
    styles = _build_styles()
    usable_w = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )
    doc._video_title = title  # type: ignore[attr-defined]

    story: list = []

    # ── Title page ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 2.5 * cm))

    if thumbnail_data:
        try:
            pil_img = PILImage.open(thumbnail_data)
            max_w = usable_w * 0.8
            aspect = pil_img.height / pil_img.width
            img_w = min(max_w, 13 * cm)
            img_h = img_w * aspect
            thumbnail_data.seek(0)
            rl_img = Image(thumbnail_data, width=img_w, height=img_h)
            rl_img.hAlign = 'CENTER'  # type: ignore[attr-defined]
            story.append(rl_img)
            story.append(Spacer(1, 1 * cm))
        except Exception:
            pass

    story.append(Paragraph(title, styles['title']))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph('A Creative Learning Notebook ✨', styles['subtitle']))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(f'Generated on {datetime.now().strftime("%B %d, %Y")}', styles['subtitle']))
    story.append(Spacer(1, 1.2 * cm))
    story.append(HRFlowable(width='70%', thickness=2.5, color=TEAL, hAlign='CENTER'))
    story.append(PageBreak())

    # ── Introduction ────────────────────────────────────────────────────────
    story.append(Paragraph('✦ Introduction', styles['chapter']))
    story.append(HRFlowable(width='100%', thickness=1.5, color=TEAL_ACCENT, spaceAfter=8))
    for para in assembled['intro'].strip().split('\n\n'):
        para = para.strip()
        if para:
            story.append(Paragraph(_clean_md(para), styles['intro']))
    story.append(Spacer(1, 0.5 * cm))

    # ── Chapters ────────────────────────────────────────────────────────────
    for chapter_text in assembled['chapters']:
        story.append(Spacer(1, 0.3 * cm))
        story.extend(_parse_section(chapter_text, styles, usable_w))

    # ── Key Takeaways ────────────────────────────────────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width='100%', thickness=2, color=TEAL))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph('✦ Key Takeaways', styles['chapter']))
    story.append(HRFlowable(width='100%', thickness=1.5, color=TEAL_ACCENT, spaceAfter=8))
    for line in assembled['summary'].strip().split('\n'):
        line = line.strip()
        if line:
            story.append(Paragraph(_clean_md(line), styles['takeaway']))

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)


# ── Public async entry point ──────────────────────────────────────────────────
async def _fetch_thumbnail(url: str) -> Optional[BytesIO]:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, timeout=10)
            if r.status_code == 200:
                return BytesIO(r.content)
        except Exception:
            pass
    return None


async def generate_pdf(
    output_path: str,
    title: str,
    thumbnail_url: str,
    assembled: dict,
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    thumbnail_data = await _fetch_thumbnail(thumbnail_url)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _build_pdf_sync, output_path, title, thumbnail_data, assembled)
