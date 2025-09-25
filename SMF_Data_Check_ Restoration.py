import os

# --- 共通のコア機能 ---

def clean_smf_packet_data(smf_packet_bytes: bytes) -> bytes:
    """
    SMFのパケット形式バイトデータからヘッダを除去し、元のファイルデータを復元する。
    """
    reconstructed_data = bytearray()
    PACKET_SIZE = 64
    HEADER_SIZE = 3
    
    packet_count = 0
    for i in range(0, len(smf_packet_bytes), PACKET_SIZE):
        packet = smf_packet_bytes[i : i + PACKET_SIZE]
        reconstructed_data.extend(packet[HEADER_SIZE:])
        packet_count += 1
    
    original_file_size = len(smf_packet_bytes) - (packet_count * HEADER_SIZE)
    return bytes(reconstructed_data[:original_file_size])

def hex_string_to_bytes(hex_str: str) -> bytes | None:
    """16進数文字列をバイトに変換する。"""
    try:
        cleaned_hex = "".join(hex_str.split())
        if not cleaned_hex: return None # 空の入力を考慮
        return bytes.fromhex(cleaned_hex)
    except ValueError:
        return None

# --- モード別の機能 ---

def reconstruct_mode():
    """モード1: SMFデータからファイルを復元する"""
    print("\n--- ファイル復元モード ---")
    
    # 手順1: 16進数データを貼り付け
    hex_dump = input("SMFの16進数データを貼り付けてください (複数行可、最後にCtrl+DまたはCtrl+Z):\n")
    smf_bytes = hex_string_to_bytes(hex_dump)
    if smf_bytes is None:
        print("エラー: データが入力されなかったか、16進数として不正です。")
        return

    # 手順2: ファイル名を入力
    base_filename = input("\n出力するファイル名（拡張子なし）を入力してください: ").strip()
    if not base_filename:
        base_filename = 'restored_file'
        print(f"-> ファイル名が未入力のため、デフォルト名 '{base_filename}' を使用します。")

    # 手順3: ファイルの種類を選択
    print("\n復元するファイルの種類を選択してください:")
    print("  1: JPG 画像")
    print("  2: H264 動画")
    
    while True:
        choice = input("番号を入力 (1 or 2): ")
        if choice in ['1', '2']:
            break
        print("!! 無効な番号です。")

    ext = '.jpg' if choice == '1' else '.h264'
    output_filename = base_filename + ext
    
    print("\n1. SMFデータからパケットヘッダを除去します...")
    clean_data = clean_smf_packet_data(smf_bytes)
    print(f"   -> 復元後のデータサイズ: {len(clean_data)} バイト")

    print(f"2. 復元したデータを '{output_filename}' に保存します...")
    with open(output_filename, 'wb') as f:
        f.write(clean_data)
    print(f"✅ 成功: '{output_filename}' を作成しました。")

def compare_mode():
    """モード2: 通常データとSMFデータを比較する"""
    print("\n--- データ比較モード ---")
    plain_hex = input("【1/2】通常のJPG/H264の16進数データを貼り付けてください:\n")
    smf_hex = input("\n【2/2】SMFの16進数データを貼り付けてください:\n")

    plain_bytes = hex_string_to_bytes(plain_hex)
    smf_bytes = hex_string_to_bytes(smf_hex)

    if plain_bytes is None or smf_bytes is None:
        print("エラー: 16進数データが不正です。")
        return

    print("\n1. SMFデータからパケットヘッダを除去します...")
    cleaned_smf_bytes = clean_smf_packet_data(smf_bytes)
    print("   -> 除去完了")
    
    print("\n2. バイトデータを比較します...")
    print(f"   - 通常データの長さ: {len(plain_bytes)} バイト")
    print(f"   - SMFデータの長さ (クリーン後): {len(cleaned_smf_bytes)} バイト")
    print("-" * 30)

    if plain_bytes == cleaned_smf_bytes:
        print("✅ 完全に一致しました。データの中身は同一です。")
    else:
        print("不一致です・・・ﾄﾞﾝ(　ﾟдﾟ)ﾏｲ")
        if len(plain_bytes) != len(cleaned_smf_bytes):
            print(f"  - バイト長が異なります。")
        
        limit = min(len(plain_bytes), len(cleaned_smf_bytes))
        for i in range(limit):
            if plain_bytes[i] != cleaned_smf_bytes[i]:
                print(f"  - 最初の相違点は {i} バイト目 (0からカウント) です。")
                print(f"    - 通常データ: {hex(plain_bytes[i])}")
                print(f"    - SMFデータ (クリーン後): {hex(cleaned_smf_bytes[i])}")
                break

# --- メインメニュー ---
def main():
    print("="*40)
    print("SMFデータ 復元・比較ツール")
    print("="*40)
    print("実行したい操作を選択してください:")
    print("  1: ファイルを復元する (SMFデータ -> JPG/H264)")
    print("  2: 2つのファイルを比較する (通常データ vs SMFデータ)")

    while True:
        choice = input("番号を入力 (1 or 2): ")
        if choice == '1':
            reconstruct_mode()
            break
        elif choice == '2':
            compare_mode()
            break
        else:
            print("!! 無効な番号です。1か2を入力してください。")

if __name__ == "__main__":
    main()