import os
import struct
import sys
from pathlib import Path
from enum import IntEnum
import re # Import regular expressions module
import csv # Added for CSV processing
from datetime import datetime # Added for timestamp processing
import traceback # Added for detailed error reporting

# --- (StatusCode and ErrorCode definitions remain the same) ---
class StatusCode(IntEnum):
    MISSION_START = 1
    MISSION_SUCCESS = 2
    DIO_TRIGGER_DETECTED = 10
    CAMERA_INITIALIZE_SUCCESS = 100
    CAPTURE_SUCCESS = 110
    MOVIE_RECORDING_SUCCESS = 120
    SAVE_SUCCESS = 200
    SMF_QUEUE_APPEND_SUCCESS = 220

class ErrorCode(IntEnum):
    UNEXPECTED_ERROR = 500
    PARAMETER_PARSE_FAIL = 501
    MISSION_EXECUTION_FAIL = 502
    CAMERA_INITIALIZE_FAIL = 600
    CAMERA_CAPTURE_TIMEOUT = 601
    CAMERA_RECOVERY_FAIL = 602
    CAMERA_FALLBACK_SUCCESS = 603
    MOVIE_RECORDING_TIMEOUT = 610
    SOURCE_FILE_NOT_FOUND = 700
    MISSION_FOLDER_CREATE_FAIL = 701
    SAVE_FAIL = 702
    MISSION_ID_OVERFLOW = 703
    MISSION_FOLDER_ALREADY_EXISTS = 704
    SOURCE_FILE_READ_FAIL = 705
    FILE_DELETE_FAIL = 706
    GPIO_SETUP_FAIL = 800
    DIO_TIMEOUT_STUCK_HIGH = 801
    DIO_TIMEOUT_WAIT_RISING = 802
    LOG_ARCHIVE_FAIL = 900
    LOG_CLEAR_FAIL = 901

code_meanings = {member.value: member.name for member in StatusCode}
code_meanings.update({member.value: member.name for member in ErrorCode})

# --- Common Core Functions ---

def clean_smf_packet_data(smf_packet_bytes: bytes) -> bytes:
    """
    Removes headers from SMF data assuming 64-byte packets with 3-byte headers.
    """
    reconstructed_data = bytearray()
    PACKET_SIZE = 64
    HEADER_SIZE = 3
    packet_count = 0
    if not smf_packet_bytes: return b''

    # Process packets in chunks of PACKET_SIZE
    for i in range(0, len(smf_packet_bytes), PACKET_SIZE):
        packet = smf_packet_bytes[i : i + PACKET_SIZE]
        if len(packet) > HEADER_SIZE:
            reconstructed_data.extend(packet[HEADER_SIZE:])
        # Keep remaining bytes if packet is smaller than header size (likely end of data)
        # This part might need adjustment based on exact packet structure rules
        # For now, keeping the partial packet if it's <= HEADER_SIZE
        elif len(packet) > 0:
             reconstructed_data.extend(packet) # Or maybe just ignore? Depends on protocol.
        packet_count += 1

    # Original size estimation logic seems overly complex and potentially error-prone.
    # The clean_smf_packet_data function should primarily focus on stripping headers.
    # The resulting size is simply the length of the reconstructed_data.
    # Let's simplify this.
    return bytes(reconstructed_data)


def hex_string_to_bytes(hex_str: str) -> bytes | None:
    """
    Cleans various hex string formats (comma-separated, space-separated,
    log dumps) and converts to bytes.
    """
    if not hex_str: return None

    # 1. Remove common log prefixes/suffixes if present
    cleaned_lines = []
    for line in hex_str.strip().splitlines():
        line = line.strip()
        if not line: continue
        # Remove ASCII part ( | ASCII...)
        if '|' in line:
            line = line.split('|')[0].strip()
        # Remove address part ( 04C31000 : ...)
        if ':' in line:
            parts = line.split(':', 1)
            # Check if the part before ':' looks like a hex address
            if len(parts[0]) >= 8 and all(c in '0123456789abcdefABCDEF' for c in parts[0].strip()):
                line = parts[1].strip() # Keep only the hex data part
            # else: keep the whole line, assuming it's just hex data

        cleaned_lines.append(line)

    # 2. Join lines and remove all non-hex characters (including commas, spaces)
    full_hex_string = "".join(cleaned_lines)
    # Use regex to keep only hex characters (0-9, a-f, A-F)
    hex_only_str = re.sub(r'[^0-9a-fA-F]', '', full_hex_string)

    # 3. Check if the result is empty or has an odd length
    if not hex_only_str:
        print("エラー: 有効な16進数データが見つかりませんでした。")
        return None
    if len(hex_only_str) % 2 != 0:
        print(f"エラー: クリーンアップ後の16進数データの長さが奇数です: '{hex_only_str[:50]}...'")
        return None

    # 4. Convert the cleaned hex string to bytes
    try:
        return bytes.fromhex(hex_only_str)
    except ValueError:
        # This error shouldn't happen if regex worked, but keep as fallback
        print(f"エラー: bytes.fromhex変換中にエラーが発生しました: '{hex_only_str[:50]}...'")
        return None
    except Exception as e:
        print(f"エラー: 16進数データの変換中に予期せぬエラー: {e}")
        return None

def parse_status_codes(data: bytes) -> list[int]:
    """
    Parses byte data into a list of 16-bit unsigned integers (status/error codes).
    """
    codes = []
    for i in range(0, len(data), 2):
        chunk = data[i:i+2]
        if len(chunk) < 2:
            print(f"警告: 最後のデータ ({chunk.hex()}) は2バイト未満のため無視されました。")
            break
        code = struct.unpack('>H', chunk)[0] # Big-endian (Network byte order)
        codes.append(code)
    return codes

# --- Mode-specific functions ---
def reconstruct_mode():
    """モード1: SMFデータからファイルを復元、またはステータスコードを解読する (手動入力)"""
    print("\n--- データ復元/解読モード (手動入力) ---")

    print("SMFの16進数データを貼り付けてください (複数行可、最後にCtrl+D(Linux/Mac)またはCtrl+Z Enter(Win)):")
    hex_lines = []
    try:
        while True:
            line = input()
            hex_lines.append(line)
    except EOFError:
        pass

    hex_dump = "\n".join(hex_lines)
    smf_bytes = hex_string_to_bytes(hex_dump) # Use the updated function

    if smf_bytes is None or len(smf_bytes) == 0:
        print("エラー: データが入力されなかったか、16進数として不正です。")
        return

    # Ask for processing type *before* cleaning, as cleaning method differs
    print("\n2. 実行したい処理を選択してください:")
    print("   1: JPG 画像として保存 (64/3パケット形式を想定)")
    print("   2: H264 動画として保存 (64/3パケット形式を想定)")
    print("   3: ステータス/エラーコードとして解読・表示 (先頭3バイトヘッダを想定)")

    while True:
        choice = input("番号を入力 (1, 2, or 3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("!! 無効な番号です。")

    # --- Clean data based on the chosen type ---
    print("\n1. SMFデータからヘッダ情報を除去します...")
    if choice == '3': # Status/Error code
        HEADER_SIZE = 3
        if len(smf_bytes) <= HEADER_SIZE:
            print("エラー：データがヘッダサイズ以下です。")
            return
        clean_data = smf_bytes[HEADER_SIZE:] # Simple slice for status codes
        print(f"   -> 先頭{HEADER_SIZE}バイトを除去しました。")
        print(f"   -> ヘッダ除去後のデータサイズ: {len(clean_data)} バイト")
    else: # File (JPG/H264)
        print("   -> 64/3パケット形式としてヘッダを除去します...")
        clean_data = clean_smf_packet_data(smf_bytes) # Use packet cleaning function
        if not clean_data:
            print("エラー：パケット除去後のデータが空になりました。入力データ形式を確認してください。")
            return
        print(f"   -> パケット除去後のファイルデータサイズ: {len(clean_data)} バイト")

    # --- Process based on choice ---
    if choice == '3':
        print("\n3. ステータス/エラーコードを解読します...")
        status_codes = parse_status_codes(clean_data)
        if status_codes:
            print("   -> 解読されたコード:")
            print(f"      {status_codes}")
            meaning_list = [f"{code} ({code_meanings.get(code, '不明なコード')})" for code in status_codes]
            print(f"      意味: {', '.join(meaning_list)}")
        else:
            print("   -> コードは見つかりませんでした（データが短いか形式が違う可能性があります）。")
        print("\n--- 処理完了 ---")
        return
    else: # File saving (choice 1 or 2)
        base_filename = input("\n3. 出力するファイル名（拡張子なし）を入力してください: ").strip()
        if not base_filename:
            base_filename = 'restored_file'
            print(f"-> ファイル名が未入力のため、デフォルト名 '{base_filename}' を使用します。")

        ext = '.jpg' if choice == '1' else '.h264'
        output_filename = base_filename + ext

        print(f"\n4. 復元したデータを '{output_filename}' に保存します...")
        try:
            with open(output_filename, 'wb') as f:
                f.write(clean_data)
            print(f"成功: '{output_filename}' を作成 ({len(clean_data)} バイト)")
        except IOError as e:
            print(f"エラー: ファイル '{output_filename}' の保存に失敗しました: {e}")
        print("\n--- 処理完了 ---")

def compare_mode():
    """モード2: 2つの16進数データを比較する (手動入力)"""
    print("\n--- データ比較モード ---")
    print("【1/2】通常のJPG/H264/StatusCode等の16進数データを貼り付けてください (複数行可、最後にCtrl+D/Z):")
    plain_hex_lines = []
    try:
        while True: plain_hex_lines.append(input())
    except EOFError: pass
    plain_hex = "\n".join(plain_hex_lines)

    print("\n【2/2】SMFの16進数データを貼り付けてください (複数行可、最後にCtrl+D/Z):")
    smf_hex_lines = []
    try:
        while True: smf_hex_lines.append(input())
    except EOFError: pass
    smf_hex = "\n".join(smf_hex_lines)

    plain_bytes = hex_string_to_bytes(plain_hex)
    smf_bytes = hex_string_to_bytes(smf_hex)

    if plain_bytes is None or smf_bytes is None:
        print("エラー: 16進数データの入力が不正です。")
        return

    print("\n*** 比較対象に合わせてSMFデータのヘッダ除去方法を選択してください ***")
    print("   1: ヘッダが先頭3バイトのみ (ステータスコード等)")
    print("   2: 64バイトパケット/先頭3バイトヘッダ形式 (画像/動画ファイル等)")
    while True:
        clean_choice = input("番号を入力 (1 or 2): ").strip()
        if clean_choice in ['1', '2']: break
        print("!! 無効な番号です。")

    print("\n1. SMFデータからヘッダを除去します...")
    if clean_choice == '1':
        HEADER_SIZE = 3
        if len(smf_bytes) <= HEADER_SIZE:
            print("エラー：SMFデータがヘッダサイズ以下です。")
            return
        cleaned_smf_bytes = smf_bytes[HEADER_SIZE:]
        print("   -> 先頭3バイトを除去しました。")
    else: # clean_choice == '2'
        cleaned_smf_bytes = clean_smf_packet_data(smf_bytes)
        print("   -> 64/3パケット形式として除去しました。")

    print("\n2. バイトデータを比較します...")
    print(f"   - 通常データの長さ: {len(plain_bytes)} バイト")
    print(f"   - SMFデータの長さ (クリーン後): {len(cleaned_smf_bytes)} バイト")
    print("-" * 30)

    if plain_bytes == cleaned_smf_bytes: print("完全に一致!!!")
    else:
        print("不一致です・・・ﾄﾞﾝ(　ﾟдﾟ)ﾏｲ")
        if len(plain_bytes) != len(cleaned_smf_bytes): print(f"   - バイト長が異なります。")
        limit = min(len(plain_bytes), len(cleaned_smf_bytes)); diff_count = 0; max_diff_to_show = 5
        for i in range(limit):
            if plain_bytes[i] != cleaned_smf_bytes[i]:
                if diff_count < max_diff_to_show:
                    print(f"   - {diff_count+1}番目の相違点は {i} バイト目 (0からカウント) です。")
                    print(f"     - 通常データ: {hex(plain_bytes[i])}")
                    print(f"     - SMFデータ (クリーン後): {hex(cleaned_smf_bytes[i])}")
                diff_count += 1
        if diff_count == 0 and len(plain_bytes) != len(cleaned_smf_bytes): print("   - データ内容は一致する範囲で同じですが、長さが異なります。")
        elif diff_count > max_diff_to_show: print(f"   - ... 他にも {diff_count - max_diff_to_show} 箇所の相違点があります。")
        elif diff_count > 0: print(f"   - 合計 {diff_count} 箇所の相違点が見つかりました。")
    print("\n--- 処理完了 ---")

# --- New Function: Reconstruct from CSV ---
def reconstruct_from_csv():
    """モード3: CSVログファイルから指定範囲のデータを復元する"""
    print("\n--- CSVファイルからデータ復元モード ---")

    # 1. CSVファイルパスの入力
    while True:
        csv_path_str = input("CSVファイルのパスを入力してください: ").strip()
        # Handle quoted paths (common in Windows when dragging/dropping)
        csv_path_str = csv_path_str.strip('"')
        csv_path = Path(csv_path_str)
        if csv_path.is_file() and csv_path.suffix.lower() == '.csv':
            break
        else:
            print(f"!! エラー: '{csv_path_str}' が見つからないか、CSVファイルではありません。")

    # 2. 開始・終了タイムスタンプの入力
    print("\n抽出したいデータの開始時刻と終了時刻を入力してください。")
    print("形式例: 2025-10-24 21:17:42.407 (ミリ秒まで)")
    while True:
        start_time_str = input("開始時刻: ").strip()
        try:
            start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S.%f')
            break
        except ValueError:
            try: # Try without milliseconds if the first format fails
                start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
                print("   -> (ミリ秒なしで解釈しました)")
                break
            except ValueError:
                print("!! エラー: 時刻の形式が正しくありません。例に従って入力してください。")
    while True:
        end_time_str = input("終了時刻: ").strip()
        try:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S.%f')
            if end_time >= start_time:
                break
            else:
                print("!! エラー: 終了時刻は開始時刻以降である必要があります。")
        except ValueError:
            try: # Try without milliseconds
                end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
                print("   -> (ミリ秒なしで解釈しました)")
                if end_time >= start_time:
                    break
                else:
                    print("!! エラー: 終了時刻は開始時刻以降である必要があります。")
            except ValueError:
                print("!! エラー: 時刻の形式が正しくありません。例に従って入力してください。")

    # 3. 復元するファイル種類の選択
    print("\n復元するファイルの種類を選択してください:")
    print("   1: JPG 画像")
    print("   2: H264 動画")
    while True:
        file_choice = input("番号を入力 (1 or 2): ").strip()
        if file_choice in ['1', '2']:
            ext = '.jpg' if file_choice == '1' else '.h264'
            break
        else:
            print("!! 無効な番号です。")

    # 4. 出力ファイル名の入力
    base_filename = input("\n出力するファイル名（拡張子なし）を入力してください: ").strip()
    if not base_filename:
        # Generate default filename based on start time
        base_filename = f'restored_from_csv_{start_time.strftime("%Y%m%d_%H%M%S")}'
        print(f"-> ファイル名が未入力のため、デフォルト名 '{base_filename}' を使用します。")
    output_filename = base_filename + ext

    # 5. CSV読み込みとデータ抽出・結合
    print(f"\nCSVファイル '{csv_path.name}' を読み込み、指定範囲のデータを抽出・結合します...")
    reconstructed_data = bytearray()
    processed_lines = 0
    skipped_lines = 0
    # Determine data start column based on your CSV structure (byte[8] corresponds to index 10 if timestamp and tx are first two columns)
    # Let's try to find 'byte[8]' in the header for robustness
    data_start_col_index = -1

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile: # Specify encoding
            reader = csv.reader(csvfile)
            try:
                header = next(reader) # Read header row
            except StopIteration:
                print("!! エラー: CSVファイルが空か、ヘッダー行がありません。")
                return

            # Find column indices dynamically
            try:
                ts_col = header.index('timestamp')
                tx_col = header.index('tx')
                # Find the index of 'byte[8]'
                data_start_header = 'byte[8]'
                if data_start_header in header:
                    data_start_col_index = header.index(data_start_header)
                else:
                    # Fallback if 'byte[8]' is not found (assuming fixed structure)
                    # Check if enough columns exist for a potential fixed structure
                    potential_fixed_index = 10 # Assuming timestamp(0), tx(1), byte[0]..byte[7] (8 cols) -> index 10
                    if len(header) > potential_fixed_index:
                        print(f"!! 警告: ヘッダーに '{data_start_header}' が見つかりません。列インデックス {potential_fixed_index} からデータを読み込みます。")
                        data_start_col_index = potential_fixed_index
                    else:
                        print(f"!! エラー: ヘッダーに '{data_start_header}' が見つからず、列数も足りません。データ開始位置を特定できません。")
                        return

            except ValueError as e:
                print(f"!! エラー: CSVヘッダーに必要な列 ('timestamp', 'tx', or '{data_start_header}') が見つかりません: {e}。処理を中断します。")
                return

            # --- Read data rows ---
            for row_num, row in enumerate(reader, start=2): # start=2 because header is line 1
                if not row or len(row) <= max(ts_col, tx_col, data_start_col_index):
                    # print(f"!! 警告: 行 {row_num} は空または列数が不足しています。スキップします。")
                    skipped_lines += 1
                    continue # Skip empty or short rows

                try:
                    # Timestamp parsing (handle potential format variations)
                    timestamp_str = row[ts_col].strip()
                    current_time = None
                    try:
                        current_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                    except ValueError:
                        try:
                            current_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                           # print(f"!! 警告: 行 {row_num} のタイムスタンプ形式が不正です: '{timestamp_str}'。スキップします。")
                           skipped_lines += 1
                           continue # Skip rows with invalid timestamp format

                    # Check if within the specified time range
                    if start_time <= current_time <= end_time:
                        # Check if it's received data (tx=0)
                        if row[tx_col].strip() == '0':
                            # Extract and append data bytes from data_start_col_index onwards
                            has_valid_byte = False
                            for cell in row[data_start_col_index:]:
                                cell_cleaned = cell.strip()
                                if cell_cleaned: # Only process non-empty cells
                                    try:
                                        byte_val = int(cell_cleaned, 16)
                                        reconstructed_data.append(byte_val)
                                        has_valid_byte = True
                                    except ValueError:
                                        # print(f"!! 警告: 行 {row_num} に16進数でないデータが含まれます: '{cell_cleaned}'。このバイト以降は無視します。")
                                        # Stop processing bytes for this row if invalid data found
                                        break
                            if has_valid_byte:
                                processed_lines += 1
                            else:
                                # Row was within time range and tx=0, but had no valid data bytes
                                skipped_lines += 1
                        else:
                            # Tx=1 line skipped
                            skipped_lines += 1
                    elif current_time > end_time:
                        # Stop reading if timestamp exceeds end_time (assuming sorted CSV)
                        print("   -> 終了時刻に達したため、読み込みを終了します。")
                        break
                    else:
                        # Timestamp before start_time, skip
                        skipped_lines += 1

                except Exception as e:
                    # Catch other potential errors during row processing
                    # print(f"!! 警告: 行 {row_num} の処理中に予期せぬエラー: {e}。スキップします。")
                    # traceback.print_exc() # Uncomment for debugging specific row errors
                    skipped_lines += 1
                    continue

    except FileNotFoundError:
        print(f"!! エラー: CSVファイル '{csv_path}' が見つかりません。")
        return
    except Exception as e:
        print(f"!! エラー: CSVファイルの読み込み/処理中に予期せぬエラーが発生しました: {e}")
        traceback.print_exc() # Show detailed error traceback
        return

    print(f"   -> 抽出範囲内の {processed_lines} 行からデータを結合しました。")
    print(f"   -> {skipped_lines} 行は範囲外、送信データ、またはデータ抽出エラーのためスキップしました。")
    print(f"   -> 結合後の合計データサイズ: {len(reconstructed_data)} バイト")

    if not reconstructed_data:
        print("!! エラー: 指定範囲内に抽出可能なデータが見つかりませんでした。タイムスタンプ、txフラグ、データ内容を確認してください。")
        return

    # 6. ファイル保存
    print(f"\n結合したデータを '{output_filename}' に保存します...")
    try:
        with open(output_filename, 'wb') as f:
            f.write(reconstructed_data)
        print(f"成功: '{output_filename}' を作成 ({len(reconstructed_data)} バイト)")
    except IOError as e:
        print(f"エラー: ファイル '{output_filename}' の保存に失敗しました: {e}")

    print("\n--- 処理完了 ---")


# --- Main menu ---
def main():
    print("="*40); print("SMFデータ 復元/比較ツール"); print("="*40)
    print("実行したい操作を選択してください:")
    print("   1: (手動入力) ファイル復元 または ステータス/エラーコード解読")
    print("   2: (手動入力) 2つのデータを比較する")
    print("   3: (CSV入力) CSVログファイルからデータを復元") # New option
    while True:
        choice = input("番号を入力 (1, 2, or 3): ").strip()
        if choice == '1': reconstruct_mode(); break
        elif choice == '2': compare_mode(); break
        elif choice == '3': reconstruct_from_csv(); break # Call the new function
        else: print("!! 無効な番号です。1, 2, 3 のいずれかを入力してください。")

if __name__ == "__main__":
    main()