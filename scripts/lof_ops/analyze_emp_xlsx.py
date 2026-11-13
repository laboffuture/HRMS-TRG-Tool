"""
Inspect the employee Excel file shared by the user.
"""
import io
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

PATH = r"C:\Users\TRG-LOF-131-047\Downloads\Emp Details for CS.xlsx"

try:
    import openpyxl
except ImportError:
    print("openpyxl not installed in this venv")
    sys.exit(1)

wb = openpyxl.load_workbook(PATH, data_only=True, read_only=False)

print("=" * 78)
print(f"FILE: {PATH}")
print("=" * 78)
print(f"Sheets: {wb.sheetnames}\n")

for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    print("=" * 78)
    print(f"SHEET: {sheet_name}")
    print(f"Dimensions: {ws.max_row} rows x {ws.max_column} cols")
    print("=" * 78)

    # Header row(s) — try first 2 rows
    print("\n--- First 3 rows (potential headers) ---")
    for row_idx in range(1, min(4, ws.max_row + 1)):
        row_vals = [str(ws.cell(row=row_idx, column=c).value)
                    for c in range(1, ws.max_column + 1)]
        print(f"  Row {row_idx}: {row_vals}")

    print(f"\n--- Sample of next 10 data rows ---")
    for row_idx in range(2, min(12, ws.max_row + 1)):
        row_vals = [ws.cell(row=row_idx, column=c).value
                    for c in range(1, ws.max_column + 1)]
        print(f"  Row {row_idx}: {row_vals}")

    # Show distinct values per column for small columns (good for spotting categorical fields)
    print("\n--- Per-column overview ---")
    for c in range(1, ws.max_column + 1):
        vals = []
        for row_idx in range(2, ws.max_row + 1):
            v = ws.cell(row=row_idx, column=c).value
            if v is not None and str(v).strip():
                vals.append(v)
        unique = list({str(v) for v in vals})
        col_letter = openpyxl.utils.get_column_letter(c)
        header = ws.cell(row=1, column=c).value
        sample_uniq = unique[:5]
        print(f"  Col {col_letter} ({header!r}): {len(vals)} non-empty, "
              f"{len(unique)} distinct, sample: {sample_uniq}")
