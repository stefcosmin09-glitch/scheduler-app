from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import cm
import io
from datetime import datetime

def generate_invoice(job, user):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph(f"<b>INVOICE</b>", styles['Title']))
    elements.append(Spacer(1, 0.5*cm))

    # Info meșter și client
    info_data = [
        ['From:', user.username],
        ['Email:', user.email],
        ['', ''],
        ['To:', job.client_name],
        ['Client Email:', job.client_email or 'N/A'],
        ['Address:', job.address],
        ['', ''],
        ['Invoice Date:', datetime.now().strftime('%d/%m/%Y')],
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

    # Detalii job
    elements.append(Paragraph("<b>Job Details</b>", styles['Heading2']))
    elements.append(Spacer(1, 0.3*cm))

    job_data = [
        ['Description', 'Amount'],
        [job.description or job.activity_type, f'£{job.price:.2f}'],
        ['', ''],
        ['TOTAL', f'£{job.price:.2f}'],
    ]

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

    # Footer
    elements.append(Paragraph("Thank you for your business!", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer