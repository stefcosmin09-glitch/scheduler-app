from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import cm
import io
from datetime import datetime, timedelta
from app import format_money

def generate_invoice(job, user):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    elements = []

    # Get business profile
    business = user.business

    # Business name
    business_name = (business.trading_name or business.legal_name) if business else user.username
    business_email = (business.business_email) if business else user.email
    business_address = (business.address or '') if business else ''
    business_phone = (business.phone or '') if business else ''

    # Invoice number
    if business:
        invoice_number = f"{business.invoice_prefix}-{str(business.next_invoice_number).zfill(6)}"
    else:
        invoice_number = f"INV-{str(job.id).zfill(6)}"

    # Due date
    issue_date = datetime.now()
    if business and business.payment_terms:
        days = int(business.payment_terms)
        due_date = issue_date + timedelta(days=days)
    else:
        due_date = issue_date + timedelta(days=30)

         # Tax calculation
    subtotal = float(job.price or 0)
    tax_amount = 0
    tax_country = (business.tax_country if business else 'UK') or 'UK'
    tax_labels = {'UK': 'VAT', 'USA': 'Sales Tax', 'RO': 'TVA'}
    tax_label = tax_labels.get(tax_country, 'VAT')
    tax_rate = float(business.vat_rate) if business and business.vat_rate else 0
    if business and business.vat_registered and tax_rate:
        tax_amount = subtotal * tax_rate / 100
    total = subtotal + tax_amount

    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph(f"<b>INVOICE</b>", styles['Title']))
    elements.append(Paragraph(f"<b>{invoice_number}</b>", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))

    # Business + Invoice info
    info_data = [
        ['FROM:', business_name],
        ['Address:', business_address],
        ['Phone:', business_phone],
        ['Email:', business_email],
    ]

    if business and business.vat_registered and business.vat_number:
        tax_no_labels = {'UK': 'VAT No:', 'USA': 'Sales Tax ID:', 'RO': 'Nr. TVA:'}
        info_data.append([tax_no_labels.get(tax_country, 'VAT No:'), business.vat_number])

    info_data += [
        ['', ''],
        ['TO:', job.client_name],
        ['Client Email:', job.client_email or 'N/A'],
        ['Address:', job.address],
        ['', ''],
        ['Invoice Date:', issue_date.strftime('%d/%m/%Y')],
        ['Due Date:', due_date.strftime('%d/%m/%Y')],
        ['Job Date:', job.date.strftime('%d/%m/%Y %H:%M')],
    ]

    info_table = Table(info_data, colWidths=[4*cm, 12*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 1*cm))

    # Job Details
    elements.append(Paragraph("<b>Job Details</b>", styles['Heading2']))
    elements.append(Spacer(1, 0.3*cm))

    job_data = [
        ['Description', 'Amount'],
        [job.description or job.activity_type, format_money(subtotal, user.currency)],
    ]

    if tax_amount > 0:
        job_data.append(['Subtotal', format_money(subtotal, user.currency)])
        job_data.append([f'{tax_label} ({tax_rate}%)', format_money(tax_amount, user.currency)])

    job_data.append(['', ''])
    job_data.append(['TOTAL DUE', format_money(total, user.currency)])

    job_table = Table(job_data, colWidths=[12*cm, 4*cm])
    job_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2563EB')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#F3F4F6')),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
    ]))
    elements.append(job_table)
    elements.append(Spacer(1, 1*cm))

    # Payment terms
    if business and business.payment_terms == '0':
        elements.append(Paragraph("Payment due on receipt.", styles['Normal']))
    else:
        elements.append(Paragraph(f"Payment due within {business.payment_terms if business else 30} days.", styles['Normal']))

    # Bank details
    if business and business.show_bank_details and business.account_name:
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph("<b>Payment Details</b>", styles['Heading2']))
        bank_data = [
            ['Account Name:', business.account_name],
            ['Sort Code:', business.sort_code or ''],
            ['Account Number:', business.account_number or ''],
        ]
        bank_table = Table(bank_data, colWidths=[4*cm, 12*cm])
        bank_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(bank_table)

    elements.append(Spacer(1, 1*cm))
    elements.append(Paragraph("Thank you for your business!", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer