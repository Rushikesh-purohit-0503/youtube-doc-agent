import asyncio
import os
import re
from dataclasses import dataclass
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

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm


# ── Themes ────────────────────────────────────────────────────────────────────

@dataclass
class _Theme:
    name: str
    page_bg: HexColor
    primary: HexColor       # title, chapter headings
    accent: HexColor        # horizontal rules, decorative lines
    body: HexColor          # body text
    example_bg: HexColor
    example_border: HexColor
    footer: HexColor
    cover_label: str
    example_label: str


_THEMES: Dict[str, _Theme] = {
    'storybook': _Theme(
        name='storybook',
        page_bg=HexColor('#FFF8E7'),
        primary=HexColor('#1A535C'),
        accent=HexColor('#4ECDC4'),
        body=HexColor('#1A1A1A'),
        example_bg=HexColor('#FFFDE0'),
        example_border=HexColor('#E0C800'),
        footer=HexColor('#888888'),
        cover_label='A Creative Learning Notebook ✨',
        example_label='💡 Real Example',
    ),
    'professional': _Theme(
        name='professional',
        page_bg=HexColor('#FFFFFF'),
        primary=HexColor('#1B2A4A'),
        accent=HexColor('#C9A227'),
        body=HexColor('#1A1A1A'),
        example_bg=HexColor('#EEF2FF'),
        example_border=HexColor('#4A6FBF'),
        footer=HexColor('#9E9E9E'),
        cover_label='Executive Video Summary',
        example_label='▸ Key Insight',
    ),
    'academic': _Theme(
        name='academic',
        page_bg=HexColor('#F7F5F0'),
        primary=HexColor('#2C3E50'),
        accent=HexColor('#8B1A1A'),
        body=HexColor('#2C2C2C'),
        example_bg=HexColor('#FFF9F0'),
        example_border=HexColor('#8B1A1A'),
        footer=HexColor('#888888'),
        cover_label='Academic Study Notes',
        example_label='Example',
    ),
    'minimal': _Theme(
        name='minimal',
        page_bg=HexColor('#FFFFFF'),
        primary=HexColor('#111111'),
        accent=HexColor('#CCCCCC'),
        body=HexColor('#333333'),
        example_bg=HexColor('#F5F5F5'),
        example_border=HexColor('#E0E0E0'),
        footer=HexColor('#AAAAAA'),
        cover_label='Video Notes',
        example_label='Example',
    ),
}

DEFAULT_THEME = 'storybook'


# ── Styles ────────────────────────────────────────────────────────────────────

def _build_styles(theme: _Theme) -> Dict[str, ParagraphStyle]:
    return {
        'title': ParagraphStyle(
            'Title_', fontName='Helvetica-Bold', fontSize=28,
            textColor=theme.primary, alignment=TA_CENTER, spaceAfter=16, leading=36,
        ),
        'subtitle': ParagraphStyle(
            'Sub_', fontName='Helvetica', fontSize=13,
            textColor=theme.body, alignment=TA_CENTER, spaceAfter=8,
        ),
        'chapter': ParagraphStyle(
            'Ch_', fontName='Helvetica-Bold', fontSize=17,
            textColor=theme.primary, spaceBefore=18, spaceAfter=6, leading=22,
        ),
        'body': ParagraphStyle(
            'Body_', fontName='Helvetica', fontSize=11,
            textColor=theme.body, spaceAfter=8, leading=16, alignment=TA_JUSTIFY,
        ),
        'bullet': ParagraphStyle(
            'Bullet_', fontName='Helvetica', fontSize=11,
            textColor=theme.body, spaceAfter=5, leading=16,
            leftIndent=24, firstLineIndent=-12,
        ),
        'example_label': ParagraphStyle(
            'ExL_', fontName='Helvetica-Bold', fontSize=11,
            textColor=theme.primary, spaceAfter=4,
        ),
        'example_body': ParagraphStyle(
            'ExB_', fontName='Helvetica-Oblique', fontSize=11,
            textColor=HexColor('#3A3A3A'), leading=16,
        ),
        'intro': ParagraphStyle(
            'Intro_', fontName='Helvetica', fontSize=12,
            textColor=theme.body, spaceAfter=12, leading=18, alignment=TA_JUSTIFY,
        ),
        'takeaway': ParagraphStyle(
            'TK_', fontName='Helvetica', fontSize=12,
            textColor=theme.body, spaceAfter=8, leading=18, leftIndent=20,
        ),
    }


# ── Page background + footer ─────────────────────────────────────────────────

def _make_on_page(theme: _Theme):
    def _on_page(canvas_obj, doc) -> None:
        canvas_obj.saveState()

        # Page background
        canvas_obj.setFillColor(theme.page_bg)
        canvas_obj.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        page_num = canvas_obj.getPageNumber()

        # Professional template: dark header band on cover
        if page_num == 1 and theme.name == 'professional':
            canvas_obj.setFillColor(theme.primary)
            canvas_obj.rect(0, PAGE_H - 3.5 * cm, PAGE_W, 3.5 * cm, fill=1, stroke=0)
            canvas_obj.setFillColor(theme.accent)
            canvas_obj.rect(0, PAGE_H - 3.6 * cm, PAGE_W, 0.1 * cm, fill=1, stroke=0)

        if page_num > 1:
            # Top accent line
            canvas_obj.setStrokeColor(theme.accent)
            canvas_obj.setLineWidth(2)
            canvas_obj.line(MARGIN, PAGE_H - 18 * mm, PAGE_W - MARGIN, PAGE_H - 18 * mm)

            # Footer
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.setFillColor(theme.footer)
            title: str = getattr(doc, '_video_title', '')
            if len(title) > 65:
                title = title[:62] + '...'
            canvas_obj.drawString(MARGIN, 14 * mm, title)
            canvas_obj.drawRightString(PAGE_W - MARGIN, 14 * mm, f'Page {page_num - 1}')

        canvas_obj.restoreState()

    return _on_page


# ── Markdown → ReportLab helpers ─────────────────────────────────────────────

def _clean_md(text: str) -> str:
    # Strip ALL raw HTML from LLM output — we apply our own properly-nested tags below.
    # Keeping LLM-generated HTML risks wrong nesting order (e.g. <b><i>…</b></i>)
    # which causes ReportLab's strict XML parser to raise ValueError.
    text = re.sub(r'<[^>]+>', '', text)
    # Bold + italic together must be handled before either alone to get correct nesting
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text, flags=re.DOTALL)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'<font name="Courier">\1</font>', text)
    return text


def _add_example_box(
    flowables: list,
    text: str,
    theme: _Theme,
    styles: dict,
    usable_w: float,
) -> None:
    rows = [
        [Paragraph(theme.example_label, styles['example_label'])],
        [Paragraph(text or '(See the video for this example)', styles['example_body'])],
    ]
    t = Table(rows, colWidths=[usable_w - 24])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), theme.example_bg),
        ('BOX', (0, 0), (-1, -1), 1.2, theme.example_border),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    flowables.append(Spacer(1, 6))
    flowables.append(t)
    flowables.append(Spacer(1, 6))


def _parse_section(
    text: str,
    theme: _Theme,
    styles: dict,
    usable_w: float,
) -> List:
    flowables: list = []
    lines = text.strip().split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.startswith('## ') or line.startswith('### '):
            prefix = 3 if line.startswith('## ') else 4
            flowables.append(Paragraph(_clean_md(line[prefix:]), styles['chapter']))
            flowables.append(HRFlowable(
                width='100%', thickness=1.5, color=theme.accent, spaceAfter=4,
            ))

        elif line.startswith('# '):
            flowables.append(Paragraph(_clean_md(line[2:]), styles['chapter']))
            flowables.append(HRFlowable(
                width='100%', thickness=1.5, color=theme.accent, spaceAfter=4,
            ))

        elif re.match(r'^[-*•▸▪]\s', line):
            bullet_text = _clean_md(re.sub(r'^[-*•▸▪]\s+', '', line))
            flowables.append(Paragraph(f'▪  {bullet_text}', styles['bullet']))

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
            _add_example_box(flowables, ' '.join(example_lines), theme, styles, usable_w)
            continue

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
            _add_example_box(flowables, ' '.join(example_lines), theme, styles, usable_w)
            continue

        else:
            clean = _clean_md(line)
            if clean:
                flowables.append(Paragraph(clean, styles['body']))

        i += 1

    return flowables


# ── Synchronous PDF build ─────────────────────────────────────────────────────

def _build_pdf_sync(
    output_path: str,
    title: str,
    thumbnail_data: Optional[BytesIO],
    assembled: dict,
    theme: _Theme,
) -> None:
    styles = _build_styles(theme)
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

    # ── Cover page ──────────────────────────────────────────────────────────
    # Extra spacer for professional template to clear the header band
    story.append(Spacer(1, 3.5 * cm if theme.name == 'professional' else 2.5 * cm))

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
    story.append(Paragraph(theme.cover_label, styles['subtitle']))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        f'Generated on {datetime.now().strftime("%B %d, %Y")}', styles['subtitle'],
    ))
    story.append(Spacer(1, 1.2 * cm))
    story.append(HRFlowable(
        width='70%', thickness=2.5, color=theme.primary, hAlign='CENTER',
    ))
    story.append(PageBreak())

    # ── Introduction ────────────────────────────────────────────────────────
    story.append(Paragraph('✦ Introduction', styles['chapter']))
    story.append(HRFlowable(
        width='100%', thickness=1.5, color=theme.accent, spaceAfter=8,
    ))
    for para in assembled['intro'].strip().split('\n\n'):
        para = para.strip()
        if para:
            story.append(Paragraph(_clean_md(para), styles['intro']))
    story.append(Spacer(1, 0.5 * cm))

    # ── Chapters ────────────────────────────────────────────────────────────
    for chapter_text in assembled['chapters']:
        story.append(Spacer(1, 0.3 * cm))
        story.extend(_parse_section(chapter_text, theme, styles, usable_w))

    # ── Key Takeaways ────────────────────────────────────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width='100%', thickness=2, color=theme.primary))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph('✦ Key Takeaways', styles['chapter']))
    story.append(HRFlowable(
        width='100%', thickness=1.5, color=theme.accent, spaceAfter=8,
    ))
    for line in assembled['summary'].strip().split('\n'):
        line = line.strip()
        if line:
            story.append(Paragraph(_clean_md(line), styles['takeaway']))

    on_page = _make_on_page(theme)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


# ── Thumbnail fetch ───────────────────────────────────────────────────────────

def _fallback_urls(url: str) -> list:
    urls = [url]
    if 'ytimg.com' in url or 'youtube.com' in url:
        for quality in ('sddefault.jpg', 'hqdefault.jpg', 'mqdefault.jpg'):
            fallback = re.sub(r'[^/]+\.jpg$', quality, url)
            if fallback not in urls:
                urls.append(fallback)
    return urls


async def _fetch_thumbnail(url: str) -> Optional[BytesIO]:
    if not url:
        return None
    async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
        for candidate in _fallback_urls(url):
            try:
                r = await client.get(candidate, timeout=10)
                if r.status_code == 200 and r.content:
                    return BytesIO(r.content)
            except Exception:
                continue
    return None


# ── Public async entry point ──────────────────────────────────────────────────

async def generate_pdf(
    output_path: str,
    title: str,
    thumbnail_url: str,
    assembled: dict,
    template: str = DEFAULT_THEME,
) -> None:
    theme = _THEMES.get(template, _THEMES[DEFAULT_THEME])
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    thumbnail_data = await _fetch_thumbnail(thumbnail_url)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _build_pdf_sync, output_path, title, thumbnail_data, assembled, theme,
    )
