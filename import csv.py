import csv

input_path = r'C:\Users\32456\Desktop\log_log4\Book2.csv'
output_path = r'C:\Users\32456\Desktop\log_log4\Book11_fixed.csv'

def normalize_hex(cell):
    cell = cell.strip()
    if not cell:  # 空欄ならそのまま
        return ""
    try:
        # 16進数 or 10進数を判定して変換
        value = int(cell, 16 if all(c in "0123456789ABCDEFabcdef" for c in cell) else 10)
        return f"{value:02X}"
    except ValueError:
        # 変換できないものはそのまま返す
        return cell

with open(input_path, newline='', encoding='utf-8') as infile, \
    open(output_path, 'w', newline='', encoding='utf-8') as outfile:
    
    reader = csv.reader(infile, delimiter='\t')  # ← タブ区切りで読む！
    writer = csv.writer(outfile, delimiter='\t', quoting=csv.QUOTE_NONE)
    
    for row in reader:
        fixed_row = [normalize_hex(cell) for cell in row]
        writer.writerow(fixed_row)

print("✅ 正常に変換が完了しました！")
print("📄 出力ファイル:", output_path)
