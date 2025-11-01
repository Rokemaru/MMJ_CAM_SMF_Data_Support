import re

def normalize_hex_input(raw_input: str) -> str:
    """
    手動入力された16進数データを自動補正する。
    1桁の値はゼロ埋めして2桁化する。
    """
    # 区切り文字で分割（スペース、タブ、改行など）
    tokens = re.split(r'[\s,]+', raw_input.strip())
    fixed_tokens = []

    for t in tokens:
        if not t:
            continue
        t = t.strip()
        # 英大文字化
        t = t.upper()
        # 16進数以外はスキップ
        if not re.fullmatch(r'[0-9A-F]+', t):
            print(f"⚠️ 無視: '{t}' は16進数ではありません。")
            continue
        # 1桁ならゼロ埋め
        if len(t) == 1:
            t = '0' + t
        elif len(t) > 2:
            print(f"⚠️ 警告: '{t}' は2桁超え。切り捨て。")
            t = t[:2]
        fixed_tokens.append(t)

    fixed_str = ''.join(fixed_tokens)
    # 最後に偶数桁かチェック
    if len(fixed_str) % 2 != 0:
        print(f"⚠️ 自動補正後も桁が奇数 ({len(fixed_str)})。末尾を削除。")
        fixed_str = fixed_str[:-1]

    return fixed_str





# --- 使用例 ---
if __name__ == "__main__":
    print("--- データ復元/解読モード (手動入力) ---")
    print("SMFの16進数データを貼り付けてください（複数行可、Ctrl+Zで終了）:")

    # 複数行入力の受け取り
    import sys
    raw_data = sys.stdin.read()

    # 自動補正を適用
    fixed_hex = normalize_hex_input(raw_data)
    print(f"\n✅ クリーンアップ済み16進数データ ({len(fixed_hex)} 桁):")
    print(fixed_hex[:200] + ("..." if len(fixed_hex) > 200 else ""))

    # バイナリ化して書き出し
    with open("チバニー_00.jpg", "wb") as f:
        f.write(bytes.fromhex(fixed_hex))
    print("✅ JPEGファイル 'recovered.jpg' を作成しました。")