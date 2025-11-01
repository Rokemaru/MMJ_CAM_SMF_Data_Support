import re
import sys
import traceback
from pathlib import Path

def normalize_hex_input(raw_input: str) -> str:
    """
    手動入力された16進数データを自動補正する。
    1桁の値はゼロ埋めして2桁化する。
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
            print(f"⚠️ 警告: '{t}' は2桁超え。切り捨て。")
            t = t[:2]
        fixed_tokens.append(t)

    fixed_str = ''.join(fixed_tokens)
    if len(fixed_str) % 2 != 0:
        print(f"⚠️ 自動補正後も桁が奇数 ({len(fixed_str)})。末尾を削除。")
        fixed_str = fixed_str[:-1]

    return fixed_str


def save_binary_file(hex_string: str, filename: str):
    """16進文字列をバイナリ化して指定ファイルに保存"""
    try:
        data_bytes = bytes.fromhex(hex_string)
    except ValueError as e:
        print(f"❌ エラー: 16進数データを変換できませんでした: {e}")
        return False

    try:
        with open(filename, "wb") as f:
            f.write(data_bytes)
        print(f"✅ ファイル '{filename}' を作成しました ({len(data_bytes)} バイト)")
        return True
    except Exception as e:
        print(f"❌ エラー: ファイル '{filename}' の保存に失敗: {e}")
        traceback.print_exc()
        return False


def main():
    print("\n--- SMF/Hex データ → JPG 復元ツール ---")
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

    filename = input("保存するファイル名を入力してください（例: output.jpg）: ").strip()
    if not filename:
        filename = "recovered.jpg"

    if not Path(filename).suffix:
        filename += ".jpg"

    print(f"\n📂 出力ファイル: {filename}")
    success = save_binary_file(fixed_hex, filename)
    if success:
        print("🎉 復元完了！")
    else:
        print("⚠️ 復元に失敗しました。")


if __name__ == "__main__":
    main()
