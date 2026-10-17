"""Per-trade landing pages used for Google Ads.

Each entry drives one URL (/electricians, /plumbers, ...). Add a new trade by
adding a key here and a route in routes.py. No invented claims: the pain points
are generic to the trade and the proof points are things the app actually does.
"""

TRADES = {
    'electricians': {
        'slug': 'electricians',
        'title': 'Invoicing and job app for UK electricians',
        'h1': 'Invoicing and job management for UK electricians',
        'pain_points': [
            'Quotes scribbled on the back of a receipt, then retyped at 9pm.',
            'Invoices that take a week to send, so payments take another week.',
            'Chasing late payments while you are on the next job.',
            'Expenses and receipts scattered across the van and your inbox.',
        ],
        'solution': 'Book the job, send the quote, invoice with VAT and take payment online, all from your phone. Customers pay from the invoice link. Reminders go out on their own. Expenses are tracked against each job.',
    },
    'plumbers': {
        'slug': 'plumbers',
        'title': 'Invoicing and job app for UK plumbers',
        'h1': 'Invoicing and job management for UK plumbers',
        'pain_points': [
            'Call-out jobs booked by text, then forgotten by Friday.',
            'Quotes sent days later, if at all.',
            'Chasing unpaid invoices between jobs.',
            'No clear view of what you actually earned this month.',
        ],
        'solution': 'Log the job on site, send the quote in minutes, invoice with VAT and get paid online. See what is owed and what is paid in one place. Reminders handle the chasing.',
    },
    'builders': {
        'slug': 'builders',
        'title': 'Invoicing and job app for UK builders',
        'h1': 'Invoicing and job management for UK builders',
        'pain_points': [
            'Big jobs, lots of materials, and the paperwork never keeps up.',
            'Quotes that take an evening to write up.',
            'Invoices late, payments later.',
            'VAT and expenses reconciled at year end by hand.',
        ],
        'solution': 'Track each job and its costs, send professional quotes and VAT invoices, take payments online and export reports for your accountant. Everything in one place.',
    },
    'roofers': {
        'slug': 'roofers',
        'title': 'Invoicing and job app for UK roofers',
        'h1': 'Invoicing and job management for UK roofers',
        'pain_points': [
            'Quotes agreed on the roof, written up later, sometimes not at all.',
            'Invoices that go out weeks after the job.',
            'Customers who pay when reminded, not before.',
            'No single place to see every job and what you are owed.',
        ],
        'solution': 'Create the job on site, send the quote and invoice with VAT, take payment online and let reminders chase the late ones. See every job and every pound owed.',
    },
}