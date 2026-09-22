import os
import io
from datetime import datetime, timedelta
from xml.sax.saxutils import escape as esc

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_RIGHT, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app import format_money

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
pdfmetrics.registerFont(TTFont('DejaVu', os.path.join(_FONT_DIR, 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVu-Bold', os.path.join(_FONT_DIR, 'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('DejaVu', normal='DejaVu', bold='DejaVu-Bold')

NAVY = colors.HexColor('#1E3A8A')
BLUE = colors.HexColor('#2563EB')
SKY = colors.HexColor('#EFF6FF')
LIGHT = colors.HexColor('#F8FAFC')
LINE = colors.HexColor('#E2E8F0')
DARK = colors.HexColor('#0F172A')
MUTED = colors.HexColor('#64748B')
C_LIGHT = colors.HexColor('#CBD5E1')

def generate_invoice(job, user, invoice=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.3*cm, bottomMargin=1.9*cm,
                            title='Invoice', author='TradeScheduler')
    W = doc.width

    business = user.business
    lang = user.language or 'en'

    L = {
        'title': 'FACTURĂ' if lang == 'ro' else 'INVOICE',
        'from': 'DE LA' if lang == 'ro' else 'FROM',
        'bill_to': 'CĂTRE' if lang == 'ro' else 'BILL TO',
        'invoice_no': 'Nr. factură' if lang == 'ro' else 'Invoice No',
        'invoice_date': 'Data facturii' if lang == 'ro' else 'Invoice Date',
        'due_date': 'Scadența' if lang == 'ro' else 'Due Date',
        'job_date': 'Data lucrării' if lang == 'ro' else 'Job Date',
        'description': 'Descriere' if lang == 'ro' else 'Description',
        'amount': 'Sumă' if lang == 'ro' else 'Amount',
        'subtotal': 'Subtotal',
        'total_due': 'TOTAL DE PLATĂ' if lang == 'ro' else 'TOTAL DUE',
        'payment_receipt': 'Plata la primire.' if lang == 'ro' else 'Payment due on receipt.',
        'payment_days': 'Plata în termen de' if lang == 'ro' else 'Payment due within',
        'days': 'zile.' if lang == 'ro' else 'days.',
        'payment_details': 'Detalii plată' if lang == 'ro' else 'Payment Details',
        'account_name': 'Nume cont' if lang == 'ro' else 'Account Name',
        'sort_code': 'Cod sortare' if lang == 'ro' else 'Sort Code',
        'account_number': 'Număr cont' if lang == 'ro' else 'Account Number',
        'thank_you': 'Vă mulțumim pentru colaborare!' if lang == 'ro' else 'Thank you for your business!',
    }

    business_name = (business.trading_name or business.legal_name or user.username) if business else user.username
    business_email = (business.business_email) if business else user.email
    business_address = (business.address or '') if business else ''
    business_phone = (business.phone or '') if business else ''

    invoice_curr = job.currency or user.currency or 'GBP'
    tax_country = (business.tax_country if business else 'UK') or 'UK'
    tax_labels = {'UK': 'VAT', 'USA': 'Sales Tax', 'RO': 'TVA', 'AU': 'GST'}
    tax_label = tax_labels.get(tax_country, 'VAT')
    tax_rate = float(business.vat_rate) if business and business.vat_rate else 0

    if invoice:
        # Use the stored invoice record: number, dates and amounts stay consistent
        # no matter how many times the PDF is regenerated.
        invoice_number = invoice.invoice_number
        issue_date = invoice.issue_date or datetime.now()
        due_date = invoice.due_date or (issue_date + timedelta(days=30))
        subtotal = float(invoice.subtotal or 0)
        tax_amount = float(invoice.vat_amount or 0)
        total = float(invoice.total_amount or 0)
    else:
        if business:
            invoice_number = f"{business.invoice_prefix}-{str(business.next_invoice_number).zfill(6)}"
        else:
            invoice_number = f"INV-{str(job.id).zfill(6)}"

        issue_date = datetime.now()
        if business and business.payment_terms:
            due_date = issue_date + timedelta(days=int(business.payment_terms))
        else:
            due_date = issue_date + timedelta(days=30)

        subtotal = float(job.price or 0)
        tax_amount = 0
        if business and business.vat_registered and tax_rate:
            tax_amount = subtotal * tax_rate / 100
        total = subtotal + tax_amount

    s = {}
    s['title'] = ParagraphStyle('title', fontName='DejaVu', fontSize=26, leading=30,
                                alignment=TA_RIGHT, textColor=colors.white)
    s['hdr_small'] = ParagraphStyle('hdr_small', fontName='DejaVu', fontSize=10, leading=14,
                                    alignment=TA_RIGHT, textColor=C_LIGHT)
    s['biz'] = ParagraphStyle('biz', fontName='DejaVu', fontSize=13, leading=17, textColor=colors.white)
    s['biz_small'] = ParagraphStyle('biz_small', fontName='DejaVu', fontSize=8.5, leading=12,
                                    textColor=C_LIGHT)
    s['sec'] = ParagraphStyle('sec', fontName='DejaVu', fontSize=8, leading=10, textColor=MUTED)
    s['body'] = ParagraphStyle('body', fontName='DejaVu', fontSize=9.5, leading=14, textColor=DARK)
    s['body_b'] = ParagraphStyle('body_b', fontName='DejaVu', fontSize=9.5, leading=14, textColor=DARK)
    s['amount'] = ParagraphStyle('amount', fontName='DejaVu', fontSize=9.5, leading=14,
                                 textColor=DARK, alignment=TA_RIGHT)
    s['amount_b'] = ParagraphStyle('amount_b', fontName='DejaVu', fontSize=11, leading=14,
                                   textColor=NAVY, alignment=TA_RIGHT)
    s['total_lbl'] = ParagraphStyle('total_lbl', fontName='DejaVu', fontSize=11, leading=14,
                                    textColor=DARK)

    elements = []

    # ---------- Header band ----------
    vat_note = ''
    if business and business.vat_registered and business.vat_number:
        tax_no_labels = {'UK': 'VAT No', 'USA': 'Sales Tax ID', 'RO': 'Nr. TVA', 'AU': 'ABN / GST No'}
        vat_note = f"{tax_no_labels.get(tax_country, 'VAT No')}: {esc(business.vat_number)}"

    biz_para = Paragraph(
        f"<b>{esc(business_name)}</b>" + (f"<br/>{vat_note}" if vat_note else ''),
        s['biz'])

    if business and business.logo:
        try:
            from PIL import Image as PILImage
            _img = PILImage.open(io.BytesIO(business.logo))
            _ratio = _img.width / max(_img.height, 1)
            _img.verify()
        except Exception:
            _ratio = 1.0
        logo_w = 1.7 * cm
        logo = Image(io.BytesIO(business.logo),
                     width=logo_w, height=logo_w / _ratio)
        left_cell = Table([[logo], [biz_para]], colWidths=[0.58*W])
        left_cell.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        left_content = left_cell
    else:
        left_content = biz_para

    right = f"<font size='26'><b>{esc(L['title'])}</b></font><br/>{esc(invoice_number)}"
    header = Table(
        [[left_content, Paragraph(right, s['title'])]],
        colWidths=[0.58*W, 0.42*W],
    )
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [8, 8, 0, 0]),
        ('LEFTPADDING', (0, 0), (-1, -1), 18),
        ('RIGHTPADDING', (0, 0), (-1, -1), 18),
        ('TOPPADDING', (0, 0), (-1, -1), 16),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 16),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 0.65*cm))

    # ---------- FROM / BILL TO ----------
    from_lines = [f"<b>{esc(business_name)}</b>"]
    if business_address:
        from_lines.append(esc(business_address))
    if business_phone:
        from_lines.append(esc(business_phone))
    if business_email:
        from_lines.append(esc(business_email))
    from_para = Paragraph('<br/>'.join(from_lines), s['body'])

    client_lines = [f"<b>{esc(job.client_name)}</b>"]
    if job.client_email:
        client_lines.append(esc(job.client_email))
    if job.address:
        client_lines.append(esc(job.address))
    to_para = Paragraph('<br/>'.join(client_lines), s['body'])

    meta = Table([[from_para, to_para]], colWidths=[0.5*W, 0.5*W])
    meta.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(meta)
    elements.append(Spacer(1, 0.5*cm))

    # ---------- Dates strip ----------
    dates = Table(
        [[Paragraph(L['invoice_date'], s['sec']), Paragraph(L['due_date'], s['sec']),
          Paragraph(L['job_date'], s['sec'])],
         [Paragraph(issue_date.strftime('%d/%m/%Y'), s['body_b']),
          Paragraph(due_date.strftime('%d/%m/%Y'), s['body_b']),
          Paragraph(job.date.strftime('%d/%m/%Y %H:%M'), s['body_b'])]],
        colWidths=[W/3, W/3, W/3],
    )
    dates.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
        ('LINEABOVE', (0, 0), (-1, 0), 1, LINE),
        ('LINEBELOW', (0, -1), (-1, -1), 1, LINE),
        ('LINEAFTER', (0, 0), (-1, -1), 1, LINE),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(dates)
    elements.append(Spacer(1, 0.8*cm))

    # ---------- Items ----------
    rows = [
        [Paragraph(L['description'], s['sec']), Paragraph(L['amount'], s['sec'])],
        [Paragraph(esc(job.description or job.activity_type or ''), s['body']),
         Paragraph(format_money(subtotal, invoice_curr), s['amount'])],
        ['', ''],
        [Paragraph(L['subtotal'], s['body']),
         Paragraph(format_money(subtotal, invoice_curr), s['amount'])],
    ]
    if tax_amount > 0:
        rows.append([Paragraph(f"{tax_label} ({tax_rate}%)", s['body']),
                     Paragraph(format_money(tax_amount, invoice_curr), s['amount'])])
    rows.append([Paragraph(L['total_due'], s['total_lbl']),
                 Paragraph(format_money(total, invoice_curr), s['amount_b'])])

    items = Table(rows, colWidths=[0.68*W, 0.32*W])
    items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SKY),
        ('BACKGROUND', (0, -1), (-1, -1), LIGHT),
        ('LINEBEFORE', (1, 1), (1, -1), 0.75, LINE),
        ('GRID', (0, 1), (-1, -2), 0.5, LINE),
        ('GRID', (0, -1), (-1, -1), 0.75, LINE),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(items)
    elements.append(Spacer(1, 0.7*cm))

    # ---------- Payment terms ----------
    if business and business.payment_terms == '0':
        terms = L['payment_receipt']
    else:
        terms = f"{L['payment_days']} {business.payment_terms if business else 30} {L['days']}"
    elements.append(Paragraph(esc(terms), s['body']))
    elements.append(Spacer(1, 0.3*cm))

    # ---------- Bank details ----------
    if business and business.show_bank_details and business.account_name:
        elements.append(Paragraph(L['payment_details'].upper(), s['sec']))
        elements.append(Spacer(1, 0.2*cm))
        bank = Table(
            [[Paragraph(L['account_name'], s['sec']), Paragraph(esc(business.account_name), s['body'])],
             [Paragraph(L['sort_code'], s['sec']), Paragraph(esc(business.sort_code or ''), s['body'])],
             [Paragraph(L['account_number'], s['sec']), Paragraph(esc(business.account_number or ''), s['body'])]],
            colWidths=[0.3*W, 0.7*W],
        )
        bank.setStyle(TableStyle([
            ('LINEBELOW', (1, 0), (1, -1), 0.5, LINE),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(bank)
        elements.append(Spacer(1, 0.3*cm))

    # ---------- Footer ----------
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.7)
        canvas.line(doc.leftMargin, 1.3*cm, A4[0] - doc.rightMargin, 1.3*cm)
        canvas.setFont('DejaVu', 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 1.0*cm, L['thank_you'])
        canvas.drawRightString(A4[0] - doc.rightMargin, 1.0*cm, f"Page {doc.page}")
        canvas.drawCentredString(A4[0]/2, 1.0*cm, 'TradeScheduler')
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer