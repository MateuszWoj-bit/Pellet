import argparse
import csv
import datetime as dt
from pathlib import Path

import xlsxwriter


def parse_args():
    parser = argparse.ArgumentParser(
        description="Format pellet_prices.csv into a styled Excel workbook."
    )
    parser.add_argument(
        "-i",
        "--input",
        default="pellet_prices.csv",
        help="Path to input CSV (default: pellet_prices.csv).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="pellet_prices.xlsx",
        help="Path to output XLSX (default: pellet_prices.xlsx).",
    )
    return parser.parse_args()


args = parse_args()
csv_path = str(Path(args.input).resolve())
xlsx_path = str(Path(args.output).resolve())

with open(csv_path, newline='', encoding='utf-8') as f:
    rows = list(csv.reader(f))

headers = rows[0]
data = rows[1:]

wb = xlsxwriter.Workbook(xlsx_path, {'remove_timezone': True})
ws = wb.add_worksheet('Prices')

header_fmt = wb.add_format({
    'bold': True,
    'bg_color': '#C7D7F0',
    'border': 1,
    'align': 'center',
    'valign': 'vcenter',
    'text_wrap': True,
    'font_size': 11,
})
text_fmt = wb.add_format({'border': 1})
text_alt_fmt = wb.add_format({'border': 1, 'bg_color': '#F7F9FC'})
num_fmt = wb.add_format({'num_format': '#,##0.00', 'border': 1})
num_alt_fmt = wb.add_format({'num_format': '#,##0.00', 'border': 1, 'bg_color': '#F7F9FC'})
kg_fmt = wb.add_format({'num_format': '0', 'border': 1})
kg_alt_fmt = wb.add_format({'num_format': '0', 'border': 1, 'bg_color': '#F7F9FC'})
ppk_fmt = wb.add_format({'num_format': '0.000', 'border': 1})
ppk_alt_fmt = wb.add_format({'num_format': '0.000', 'border': 1, 'bg_color': '#F7F9FC'})
price_fmt = wb.add_format({'num_format': '#,##0.00 "PLN"', 'border': 1})
price_alt_fmt = wb.add_format({'num_format': '#,##0.00 "PLN"', 'border': 1, 'bg_color': '#F7F9FC'})
date_fmt = wb.add_format({'num_format': 'yyyy-mm-dd hh:mm', 'border': 1})
date_alt_fmt = wb.add_format({'num_format': 'yyyy-mm-dd hh:mm', 'border': 1, 'bg_color': '#F7F9FC'})

sep_fmt = wb.add_format({
    'bold': True,
    'bg_color': '#EDEDED',
    'border': 1,
    'align': 'left',
})

for c, h in enumerate(headers):
    ws.write(0, c, h, header_fmt)


def parse_dt(s):
    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None

col_index = {h: i for i, h in enumerate(headers)}

last_day = None
row_cursor = 1
for row in data:
    d = parse_dt(row[col_index['fetched_at']])
    day = d.date() if d else None

    if day != last_day:
        label = f"{day.isoformat()}" if day else "(unknown date)"
        ws.write(row_cursor, 0, label, sep_fmt)
        ws.merge_range(row_cursor, 0, row_cursor, len(headers)-1, label, sep_fmt)
        row_cursor += 1
        last_day = day

    alt = (row_cursor % 2) == 0

    for c, val in enumerate(row):
        if val == '':
            ws.write_blank(row_cursor, c, None, text_alt_fmt if alt else text_fmt)
            continue

        header = headers[c]
        if header == 'fetched_at':
            if d:
                ws.write_datetime(row_cursor, c, d, date_alt_fmt if alt else date_fmt)
            else:
                ws.write(row_cursor, c, val, text_alt_fmt if alt else text_fmt)
        elif header == 'price':
            try:
                ws.write_number(row_cursor, c, float(val), price_alt_fmt if alt else price_fmt)
            except Exception:
                ws.write(row_cursor, c, val, text_alt_fmt if alt else text_fmt)
        elif header == 'kg':
            try:
                ws.write_number(row_cursor, c, float(val), kg_alt_fmt if alt else kg_fmt)
            except Exception:
                ws.write(row_cursor, c, val, text_alt_fmt if alt else text_fmt)
        elif header == 'pln_per_kg':
            try:
                ws.write_number(row_cursor, c, float(val), ppk_alt_fmt if alt else ppk_fmt)
            except Exception:
                ws.write(row_cursor, c, val, text_alt_fmt if alt else text_fmt)
        elif header == 'url':
            ws.write_url(row_cursor, c, val, text_alt_fmt if alt else text_fmt, string=val)
        else:
            ws.write(row_cursor, c, val, text_alt_fmt if alt else text_fmt)

    row_cursor += 1

ws.freeze_panes(1, 0)
ws.autofilter(0, 0, row_cursor - 1, len(headers) - 1)

ppk_col = col_index.get('pln_per_kg')
if ppk_col is not None:
    ws.conditional_format(1, ppk_col, row_cursor - 1, ppk_col, {
        'type': '3_color_scale',
        'min_color': '#63BE7B',
        'mid_color': '#FFEB84',
        'max_color': '#F8696B'
    })

widths = {
    'fetched_at': 20,
    'url': 70,
    'variant': 24,
    'price': 14,
    'kg': 8,
    'pln_per_kg': 12,
    'source': 20,
}
for c, h in enumerate(headers):
    ws.set_column(c, c, widths.get(h, 14))

wb.close()
print(xlsx_path)
