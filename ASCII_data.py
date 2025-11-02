import re
import sys
import traceback
from pathlib import Path

def normalize_hex_input(raw_input: str) -> str:
    """
    手動入力された16進数データを自動補正する。
    1桁の値はゼロ埋めして2桁化する。
    (元のスクリプトから流用)
    """
    tokens = re.split(r'[\s,]+', raw_input.strip())
    fixed_tokens = []

    for t in tokens:
        if not t:
            continue
        t = t.strip().upper()
        if not re.fullmatch(r'[0-9A-F]+', t):
            print(f"⚠️ 無視: '{t}' は16進数ではありません。")
            continue
        if len(t) == 1:
            t = '0' + t
        elif len(t) > 2:
            # 2桁ごとに区切られている場合も考慮 (例: FFEE)
            for i in range(0, len(t), 2):
                fixed_tokens.append(t[i:i+2])
            continue
        fixed_tokens.append(t)

    fixed_str = ''.join(fixed_tokens)
    
    # 注: 元のスクリプトでは奇数桁の場合末尾を削除していましたが、
    # 2桁を超える入力を許可したため、このロジックは調整が必要かもしれません。
    # ここでは、2桁単位で処理した結果をそのまま使います。
    
    # 最終チェックとして、全体の桁数が奇数なら末尾を削除
    if len(fixed_str) % 2 != 0:
        print(f"⚠️ 自動補正後も桁が奇数 ({len(fixed_str)})。末尾を削除。")
        fixed_str = fixed_str[:-1]

    return fixed_str


def convert_hex_to_ascii(hex_string: str):
    """16進文字列をASCIIテキストに変換して表示"""
    try:
        data_bytes = bytes.fromhex(hex_string)
    except ValueError as e:
        print(f"❌ エラー: 16進数データをバイトに変換できませんでした: {e}")
        return

    print("\n--- 変換結果 (ASCII) ---")
    try:
        # ASCIIとしてデコードを試みる
        # errors='replace' は、デコードできないバイトを '?' に置き換える
        decoded_text = data_bytes.decode('ascii', errors='replace')
        print(decoded_text)
        print("--------------------------")
        print(f"✅ 変換完了 ({len(data_bytes)} バイト → {len(decoded_text)} 文字)")
        
        # 制御文字や非表示文字が含まれている可能性を警告
        if any(0 <= b < 32 or b == 127 for b in data_bytes):
            print("⚠️ (注: 結果には改行やタブ、その他の制御文字が含まれている可能性があります)")
            
    except Exception as e:
        print(f"❌ エラー: ASCIIへのデコードに失敗: {e}")
        traceback.print_exc()


def main():
    print("\n--- 16進数データ → ASCII 変換ツール ---")
    print("16進数データを貼り付けてください（複数行OK、Ctrl+Zで終了）:")

    try:
        raw_data = sys.stdin.read()
    except KeyboardInterrupt:
        print("\n入力が中断されました。")
        return

    if not raw_data.strip():
        print("❌ 入力が空です。終了します。")
        return

    fixed_hex = normalize_hex_input(raw_data)
    if not fixed_hex:
        print("❌ 有効な16進数が見つかりません。")
        return

    print(f"\n✅ クリーンアップ済み16進数データ ({len(fixed_hex)} 桁)")
    preview = fixed_hex[:200] + ("..." if len(fixed_hex) > 200 else "")
    print(f"例: {preview}\n")

    convert_hex_to_ascii(fixed_hex)


if __name__ == "__main__":
    main()