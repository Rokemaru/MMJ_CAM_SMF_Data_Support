import re
import sys
import traceback
from pathlib import Path

def normalize_hex_input(raw_input: str) -> str:
    """
    手動入力された16進数データを自動補正する。
    1桁の値はゼロ埋めして2桁化する。
    """
    # 既存の正規表現を使い、スペース、コンマ、改行などで分割
    tokens = re.split(r'[\s,]+', raw_input.strip())
    fixed_tokens = []

    for t in tokens:
        if not t:
            continue
        t = t.strip().upper()
        if not re.fullmatch(r'[0-9A-F]+', t):
            print(f"⚠️ 無視: '{t}' は16進数ではありません。")
            continue
        
        # 1桁の入力をゼロ埋め（例: 'F' -> '0F'）
        if len(t) == 1:
            t = '0' + t
        # 2桁を超える入力を丸め（例: 'FFD8' -> 'FF'）
        # ただし、ヘッダー除去モードでは意図的に長いデータが
        # 入ることがあるため、この警告は状況によってノイズになる可能性あり
        elif len(t) > 2 and len(t) % 2 != 0:
            print(f"⚠️ 警告: '{t}' は奇数桁です。")
            # 奇数桁の場合は、偶数桁に丸めるなどの処理も可能だが、
            # ここではオリジナルのロジック（先頭2桁）は変更せず、
            # 偶数桁の長い入力（例: FFD8FFE0）はそのまま通すように調整
            pass
        
        # 1桁でも2桁でもない奇数桁の場合（例: 'ABC'）
        if len(t) % 2 != 0 and len(t) > 1:
             print(f"⚠️ 警告: '{t}' は奇数桁({len(t)})です。処理が不正確かも。")
             # 元のロジックでは >2 で切り捨てていた
             t = t[:2]

        # 偶数桁（2桁、4桁、...）はそのまま追加
        fixed_tokens.append(t)

    fixed_str = ''.join(fixed_tokens)
    
    # 最終的な文字列長が奇数だった場合、末尾を削る
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
    
    # --- モード選択の追加 ---
    print("解析モードを選択してください:")
    print("  1: 手動コピペモード (1桁補正などを行う)")
    print("  2: SMFヘッダー除去モード (各行の先頭24バイトを除去)")
    
    mode = input("モード (1/2): ").strip()
    
    if mode not in ['1', '2']:
        print("❌ 無効なモードです。終了します。")
        return

    print("\n16進数データを貼り付けてください（複数行OK、Ctrl+Z/Ctrl+Dで終了）:")

    try:
        raw_data = sys.stdin.read()
    except KeyboardInterrupt:
        print("\n入力が中断されました。")
        return

    if not raw_data.strip():
        print("❌ 入力が空です。終了します。")
        return

    # --- モードに応じたデータ前処理 ---
    processed_data_for_normalize = ""
    
    if mode == '1':
        # モード1: 従来通り、生データをそのまま正規化処理へ
        print("\n[モード1: 手動コピペモードで実行]")
        processed_data_for_normalize = raw_data
        
    elif mode == '2':
        # モード2: SMFヘッダー除去モード
        print("\n[モード2: SMFヘッダー除去モードで実行]")
        
        # ご指定のヘッダー「4A 53 ... 00」は 24バイト です。
        # スペース込みの文字列長は 71文字 となります。
        HEADER_CHAR_LEN = 71 
        
        payload_data = []
        lines = raw_data.splitlines()
        
        print(f"  {len(lines)} 行のデータを処理します...")
        print(f"  各行の先頭 {HEADER_CHAR_LEN} 文字（24バイト分）をヘッダーとして除去します。")
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue # 空行は無視
            
            if len(line) < HEADER_CHAR_LEN:
                print(f"⚠️ 警告 (L{i+1}): 行がヘッダー長より短いため無視します。")
                continue
                
            # 71文字目以降をペイロード（JPGデータ）として抽出
            payload = line[HEADER_CHAR_LEN:]
            payload_data.append(payload)
            
        # 抽出した全ペイロードをスペース区切りで連結し、
        # この後 normalize_hex_input に渡す
        processed_data_for_normalize = " ".join(payload_data)
        
        if not processed_data_for_normalize.strip():
            print("❌ ヘッダー除去後、有効なデータが残りませんでした。")
            return
    
    # --- 共通処理 ---
    # モード1またはモード2で前処理されたデータを正規化
    fixed_hex = normalize_hex_input(processed_data_for_normalize)
    
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