import os
import struct
import sys
from pathlib import Path
from enum import IntEnum
import re
import csv
from datetime import datetime, timedelta
import traceback

# --- StatusCode, ErrorCode, code_meanings definitions ---
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
    if not smf_packet_bytes: return b''
    try:
        for i in range(0, len(smf_packet_bytes), PACKET_SIZE):
            packet = smf_packet_bytes[i : i + PACKET_SIZE]
            if len(packet) > HEADER_SIZE:
                reconstructed_data.extend(packet[HEADER_SIZE:])
            elif len(packet) > 0:
                reconstructed_data.extend(packet) # Keep partial packet at the end
    except Exception as e:
        print(f"!! エラー: clean_smf_packet_data 処理中にエラーが発生しました: {e}")
        return b'' # Return empty bytes on error
    return bytes(reconstructed_data)

def hex_string_to_bytes(hex_str: str) -> bytes | None:
    """
    Cleans various hex string formats and converts to bytes.
    """
    if not hex_str: return None
    try:
        cleaned_lines = []
        for line in hex_str.strip().splitlines():
            line = line.strip()
            if not line: continue
            if '|' in line: line = line.split('|')[0].strip()
            if ':' in line:
                parts = line.split(':', 1)
                # Check potential hex address more carefully
                potential_addr = parts[0].strip()
                if len(potential_addr) >= 4 and all(c in '0123456789abcdefABCDEF' for c in potential_addr):
                    # Basic check passed, assume it's an address
                    line = parts[1].strip()
                # else: Keep the line as is, might be just hex data with a colon
            cleaned_lines.append(line)

        full_hex_string = "".join(cleaned_lines)
        hex_only_str = re.sub(r'[^0-9a-fA-F]', '', full_hex_string)

        if not hex_only_str:
            print("エラー: 有効な16進数データが見つかりませんでした。")
            return None
        if len(hex_only_str) % 2 != 0:
            # Try padding with a leading zero if odd length (might be accidental)
            # print(f"警告: 16進数データの長さが奇数です。先頭に'0'を補完して試みます: '{hex_only_str[:50]}...'")
            # hex_only_str = '0' + hex_only_str
            # --- OR --- return error for odd length ---
            print(f"エラー: クリーンアップ後の16進数データの長さが奇数です: '{hex_only_str[:50]}...'")
            return None

        return bytes.fromhex(hex_only_str)
    except ValueError as e:
        print(f"エラー: 16進数からバイトへの変換中にエラーが発生しました: {e}。入力データを確認してください: '{hex_only_str[:50]}...'")
        return None
    except Exception as e:
        print(f"エラー: 16進数データの処理中に予期せぬエラー: {e}")
        traceback.print_exc()
        return None

def parse_status_codes(data: bytes) -> list[int]:
    """
    Parses byte data into a list of 16-bit unsigned integers (status/error codes).
    """
    codes = []
    if not data: return codes
    try:
        for i in range(0, len(data), 2):
            chunk = data[i:i+2]
            if len(chunk) < 2:
                print(f"警告: 最後のデータ ({chunk.hex()}) は2バイト未満のため無視されました。")
                break
            # Use struct.unpack which handles potential errors during unpacking
            code = struct.unpack('>H', chunk)[0] # Big-endian
            codes.append(code)
    except struct.error as e:
        print(f"!! エラー: ステータスコードの解析中にstructエラーが発生しました: {e}")
    except Exception as e:
        print(f"!! エラー: ステータスコードの解析中に予期せぬエラー: {e}")
    return codes

# --- Helper function to parse hex string from CSV row ---
def parse_hex_bytes_from_row(row: list[str], start_index: int, num_bytes_to_attempt: int, row_num_for_err: int = -1) -> bytes | None:
    """
    指定された列インデックスから最大num_bytes_to_attemptバイト数の16進数データをバイト列として抽出。
    行末や空セルで停止し、それまでの有効なバイトを返す。不正なセルが見つかった場合はNoneを返す。
    """
    hex_parts = []
    if not row or len(row) <= start_index: # Check start index validity
        return None # Return None if starting index is out of bounds

    actual_read_limit = min(start_index + num_bytes_to_attempt, len(row))

    try:
        for i in range(start_index, actual_read_limit):
            cell = row[i].strip()
            if len(cell) == 1 and cell in '0123456789abcdefABCDEF':
                cell = '0' + cell # Pad single digit hex
            if len(cell) == 2 and all(c in '0123456789abcdefABCDEF' for c in cell):
                hex_parts.append(cell)
            elif not cell:
                # Empty cell found, stop reading for this row and return what we have
                # print(f"DEBUG (Row {row_num_for_err}): Empty cell at index {i}, stopping payload read.") # Debug
                break
            else:
                # Invalid hex character found
                if row_num_for_err > 0: print(f"!! 警告 (行 {row_num_for_err}): 列 {i} は16進数ではありません: '{row[i]}'")
                # Return None because invalid hex likely means corruption
                return None

        # If loop finished or broke due to empty cell, check if we collected anything
        if not hex_parts:
            # No valid hex found at all starting from start_index
            return None

        # Convert the collected parts
        return bytes.fromhex("".join(hex_parts))

    except ValueError as e: # Error during bytes.fromhex
        if row_num_for_err > 0: print(f"!! エラー (行 {row_num_for_err}): 16進数変換エラー: {e}")
        return None
    except Exception as e:
        if row_num_for_err > 0: print(f"!! エラー (行 {row_num_for_err}): バイト抽出中に予期せぬエラー: {e}")
        traceback.print_exc()
        return None


# --- Mode-specific functions ---
def reconstruct_mode():
    """モード1: SMFデータからファイルを復元、またはステータスコードを解読する (手動入力)"""
    print("\n--- データ復元/解読モード (手動入力) ---")
    print("SMFの16進数データを貼り付けてください (複数行可、最後にCtrl+D(Linux/Mac)またはCtrl+Z Enter(Win)):")
    hex_lines = []
    try:
        while True: hex_lines.append(input())
    except EOFError: pass
    except Exception as e:
        print(f"!! エラー: データ入力中にエラーが発生しました: {e}")
        return

    hex_dump = "\n".join(hex_lines)
    smf_bytes = hex_string_to_bytes(hex_dump)
    if smf_bytes is None or len(smf_bytes) == 0:
        print("エラー: データが入力されなかったか、16進数として不正です。")
        return

    print("\n処理の種類を選択してください:")
    print("   1: JPG 画像として保存 (64/3パケット形式を想定)")
    print("   2: H264 動画として保存 (64/3パケット形式を想定)")
    print("   3: ステータス/エラーコードとして解読・表示 (先頭3バイトヘッダを想定)")
    choice = ''
    while choice not in ['1', '2', '3']:
        choice = input("番号を入力 (1, 2, or 3): ").strip()
        if choice not in ['1', '2', '3']: print("!! 無効な番号です。")

    print("\n1. SMFデータからヘッダ情報を除去します...")
    clean_data = None
    try:
        if choice == '3':
            HEADER_SIZE = 3
            if len(smf_bytes) <= HEADER_SIZE:
                print("エラー：データがヘッダサイズ以下です。")
                return
            clean_data = smf_bytes[HEADER_SIZE:]
            print(f"   -> 先頭{HEADER_SIZE}バイトを除去しました。")
        else:
            print("   -> 64/3パケット形式としてヘッダを除去します...")
            clean_data = clean_smf_packet_data(smf_bytes)
            if not clean_data:
                print("エラー：パケット除去後のデータが空になりました。入力データ形式を確認してください。")
                return
        print(f"   -> ヘッダ除去後のデータサイズ: {len(clean_data)} バイト")
    except Exception as e:
        print(f"!! エラー: ヘッダ除去中にエラーが発生しました: {e}")
        return

    # --- Process based on choice ---
    try:
        if choice == '3':
            print("\n2. ステータス/エラーコードを解読します...")
            status_codes = parse_status_codes(clean_data)
            if status_codes:
                print("   -> 解読されたコード:")
                print(f"      {status_codes}")
                meaning_list = [f"{code} ({code_meanings.get(code, '不明なコード')})" for code in status_codes]
                print(f"      意味: {', '.join(meaning_list)}")
            else:
                print("   -> コードは見つかりませんでした（データが短いか形式が違う可能性があります）。")
        else: # File saving
            base_filename = input("\n2. 出力するファイル名（拡張子なし）を入力してください: ").strip()
            if not base_filename:
                base_filename = 'restored_file'
                print(f"-> ファイル名が未入力のため、デフォルト名 '{base_filename}' を使用します。")

            ext = '.jpg' if choice == '1' else '.h264'
            output_filename = base_filename + ext

            print(f"\n3. 復元したデータを '{output_filename}' に保存します...")
            with open(output_filename, 'wb') as f:
                f.write(clean_data)
            print(f"成功: '{output_filename}' を作成 ({len(clean_data)} バイト)")

    except IOError as e:
        print(f"エラー: ファイル '{output_filename}' の保存に失敗しました: {e}")
    except Exception as e:
        print(f"!! エラー: 処理またはファイル保存中に予期せぬエラーが発生しました: {e}")
        traceback.print_exc()

    print("\n--- 処理完了 ---")


def compare_mode():
    """モード2: 2つの16進数データを比較する (手動入力)"""
    print("\n--- データ比較モード ---")
    plain_bytes, smf_bytes = None, None
    try:
        print("【1/2】通常の16進数データを貼り付けてください (複数行可、最後にCtrl+D/Z):")
        plain_hex_lines = []
        try:
            while True: plain_hex_lines.append(input())
        except EOFError: pass
        plain_hex = "\n".join(plain_hex_lines)
        plain_bytes = hex_string_to_bytes(plain_hex)

        print("\n【2/2】SMFの16進数データを貼り付けてください (複数行可、最後にCtrl+D/Z):")
        smf_hex_lines = []
        try:
            while True: smf_hex_lines.append(input())
        except EOFError: pass
        smf_hex = "\n".join(smf_hex_lines)
        smf_bytes = hex_string_to_bytes(smf_hex)

    except Exception as e:
        print(f"!! エラー: データ入力中にエラーが発生しました: {e}")
        return

    if plain_bytes is None or smf_bytes is None:
        print("エラー: 16進数データの入力または変換に失敗しました。")
        return

    print("\n比較対象に合わせてSMFデータのヘッダ除去方法を選択してください:")
    print("   1: ヘッダが先頭3バイトのみ")
    print("   2: 64バイトパケット/先頭3バイトヘッダ形式")
    clean_choice = ''
    while clean_choice not in ['1', '2']:
        clean_choice = input("番号を入力 (1 or 2): ").strip()
        if clean_choice not in ['1', '2']: print("!! 無効な番号です。")

    print("\n1. SMFデータからヘッダを除去します...")
    cleaned_smf_bytes = None
    try:
        if clean_choice == '1':
            HEADER_SIZE = 3
            if len(smf_bytes) <= HEADER_SIZE:
                print("エラー：SMFデータがヘッダサイズ以下です。")
                return
            cleaned_smf_bytes = smf_bytes[HEADER_SIZE:]
            print("   -> 先頭3バイトを除去しました。")
        else: # clean_choice == '2'
            cleaned_smf_bytes = clean_smf_packet_data(smf_bytes)
            if cleaned_smf_bytes is None: # Check if cleaning failed
                print("エラー: SMFデータのヘッダ除去に失敗しました。")
                return
            print("   -> 64/3パケット形式として除去しました。")
    except Exception as e:
        print(f"!! エラー: ヘッダ除去中にエラーが発生しました: {e}")
        return

    print("\n2. バイトデータを比較します...")
    try:
        plain_len = len(plain_bytes)
        cleaned_len = len(cleaned_smf_bytes)
        print(f"   - 通常データの長さ: {plain_len} バイト")
        print(f"   - SMFデータの長さ (クリーン後): {cleaned_len} バイト")
        print("-" * 30)

        if plain_bytes == cleaned_smf_bytes: print("完全に一致")
        else:
            print("不一致です")
            if plain_len != cleaned_len: print(f"   - バイト長が異なります。")
            limit = min(plain_len, cleaned_len); diff_count = 0; max_diff_to_show = 5
            for i in range(limit):
                if plain_bytes[i] != cleaned_smf_bytes[i]:
                    if diff_count < max_diff_to_show:
                        print(f"   - {diff_count+1}番目の相違点は {i} バイト目 (0からカウント) です。")
                        print(f"     - 通常データ: {hex(plain_bytes[i])}")
                        print(f"     - SMFデータ (クリーン後): {hex(cleaned_smf_bytes[i])}")
                    diff_count += 1
            if diff_count == 0 and plain_len != cleaned_len: print("   - データ内容は一致する範囲で同じですが、長さが異なります。")
            elif diff_count > max_diff_to_show: print(f"   - ... 他にも {diff_count - max_diff_to_show} 箇所の相違点があります。")
            elif diff_count > 0: print(f"   - 合計 {diff_count} 箇所の相違点が見つかりました。")
    except Exception as e:
        print(f"!! エラー: データ比較中にエラーが発生しました: {e}")

    print("\n--- 処理完了 ---")

# --- Function: Reconstruct from CSV by Time Range ---
def reconstruct_from_csv():
    """モード3: CSVログファイルから指定時間範囲のデータを復元する"""
    print("\n--- CSVファイルから時間範囲でデータ復元モード ---")
    csv_path = None
    while True:
        try:
            csv_path_str = input("CSVファイルのパスを入力してください: ").strip().strip('"')
            csv_path_test = Path(csv_path_str)
            if csv_path_test.is_file() and csv_path_test.suffix.lower() == '.csv':
                csv_path = csv_path_test # Assign only if valid
                break
            else:
                print(f"!! エラー: '{csv_path_str}' が見つからないか、CSVファイルではありません。")
        except Exception as e:
            print(f"!! エラー: パス入力処理中にエラー: {e}")

    print("\n抽出したいデータの開始時刻と終了時刻を入力してください。")
    print("形式例: 2025-10-24 21:17:42.407 (ミリ秒まで)")
    start_time, end_time = None, None
    while start_time is None:
        start_time_str = input("開始時刻: ").strip()
        try: start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            try:
                start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
                print("   -> (ミリ秒なしで解釈しました)")
            except ValueError: print("!! エラー: 時刻の形式が正しくありません。")
    while end_time is None:
        end_time_str = input("終了時刻: ").strip()
        try:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S.%f')
            if end_time < start_time: print("!! エラー: 終了時刻は開始時刻以降である必要があります。"); end_time = None
        except ValueError:
            try:
                end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
                print("   -> (ミリ秒なしで解釈しました)")
                if end_time < start_time: print("!! エラー: 終了時刻は開始時刻以降である必要があります。"); end_time = None
            except ValueError: print("!! エラー: 時刻の形式が正しくありません。")

    print("\n復元するファイルの種類を選択してください:")
    print("   1: JPG 画像")
    print("   2: H264 動画")
    file_choice = ''
    while file_choice not in ['1', '2']:
        file_choice = input("番号を入力 (1 or 2): ").strip()
        if file_choice not in ['1', '2']: print("!! 無効な番号です。")
    ext = '.jpg' if file_choice == '1' else '.h264'

    base_filename = input("\n出力するファイル名（拡張子なし）を入力してください: ").strip()
    if not base_filename:
        base_filename = f'time_restored_{start_time.strftime("%Y%m%d_%H%M%S")}'
        print(f"-> ファイル名が未入力のため、デフォルト名 '{base_filename}' を使用します。")
    output_filename = base_filename + ext

    print(f"\nCSVファイル '{csv_path.name}' を読み込み、指定範囲のデータを抽出・結合します...")
    reconstructed_data = bytearray()
    processed_lines = 0; skipped_lines = 0; data_start_col_index = -1; ts_col = -1; tx_col = -1

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            try: header = next(reader)
            except StopIteration: print("!! エラー: CSVファイルが空か、ヘッダー行がありません。"); return

            try:
                ts_col = header.index('timestamp'); tx_col = header.index('tx')
                data_start_header = 'byte[24]' # Payload start column (heuristic)
                if data_start_header in header: data_start_col_index = header.index(data_start_header)
                else:
                    potential_fixed_index = 2 + 24 # ts, tx + byte[0]..byte[23]
                    if len(header) > potential_fixed_index:
                        print(f"!! 警告: ヘッダーに '{data_start_header}' が見つかりません。列インデックス {potential_fixed_index} からデータを読み込みます。")
                        data_start_col_index = potential_fixed_index
                    else: print(f"!! エラー: データ開始列 '{data_start_header}' が見つかりません。"); return
            except ValueError as e: print(f"!! エラー: CSVヘッダーに必要な列が見つかりません: {e}。"); return

            for row_num, row in enumerate(reader, start=2):
                if not row or len(row) <= max(ts_col, tx_col, data_start_col_index):
                    skipped_lines += 1; continue
                try: # Inner try for row processing
                    timestamp_str = row[ts_col].strip(); current_time = None
                    try: current_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                    except ValueError:
                        try: current_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError: skipped_lines += 1; continue # Skip row if time invalid

                    if start_time <= current_time <= end_time:
                        if row[tx_col].strip() == '0':
                            has_valid_byte = False
                            payload_bytes = parse_hex_bytes_from_row(row, data_start_col_index, len(row) - data_start_col_index, row_num)
                            if payload_bytes:
                                reconstructed_data.extend(payload_bytes)
                                processed_lines += 1
                            else:
                                # print(f"警告 (行 {row_num}): ペイロード抽出失敗。") # Debug
                                skipped_lines += 1
                        else: skipped_lines += 1
                    elif current_time > end_time:
                        print("   -> 終了時刻に達したため、読み込みを終了します。"); break
                    else: skipped_lines += 1
                except Exception as e:
                    print(f"!! 警告 (行 {row_num}): 処理エラー: {e}") # Report error for specific row
                    skipped_lines += 1; continue # Skip to next row

    except FileNotFoundError: print(f"!! エラー: CSVファイル '{csv_path}' が見つかりません。"); return
    except Exception as e: print(f"!! エラー: CSV処理中に予期せぬエラー: {e}"); traceback.print_exc(); return

    print(f"   -> 抽出範囲内の {processed_lines} 行からデータを結合。"); print(f"   -> {skipped_lines} 行スキップ。")
    print(f"   -> 結合後の合計データサイズ: {len(reconstructed_data)} バイト")
    if not reconstructed_data: print("!! エラー: 指定範囲内に抽出可能なデータが見つかりませんでした。"); return

    print(f"\n結合したデータを '{output_filename}' に保存します...")
    try:
        with open(output_filename, 'wb') as f: f.write(reconstructed_data)
        print(f"成功: '{output_filename}' を作成 ({len(reconstructed_data)} バイト)")
    except IOError as e: print(f"エラー: ファイル '{output_filename}' の保存に失敗: {e}")
    except Exception as e: print(f"!! エラー: ファイル保存中に予期せぬエラー: {e}")

    print("\n--- 処理完了 ---")


# --- UPDATED Function: Reconstruct from CSV using Command Info (using Downlink Data Packet Format) ---
def reconstruct_from_csv_command():
    """モード4: CSVログからコマンド情報を元にデータを復元し、欠損チェックを行う (ACK経由, ダウンリンクデータフォーマット対応)"""
    print("\n--- CSVファイルからコマンド基準でデータ復元 (ACK経由, ダウンリンクデータフォーマット対応) ---")

    # 1. Get CSV file path
    csv_path = None
    while True:
        try:
            csv_path_str = input("CSVファイルのパスを入力してください: ").strip().strip('"')
            csv_path_test = Path(csv_path_str)
            if csv_path_test.is_file() and csv_path_test.suffix.lower() == '.csv':
                csv_path = csv_path_test; break
            else: print(f"!! エラー: '{csv_path_str}' が見つからないか、CSVファイルではありません。")
        except Exception as e: print(f"!! エラー: パス入力処理中にエラー: {e}")

    # --- CSV Constants (Updated for Downlink Data Format) ---
    TS_COL = 0; TX_COL = 1; BYTE0_COL = 2
    CMD_PREFIX = b'\x4D\x00\x12'
    CMD_PREFIX_START_REL = 0; CMD_PREFIX_LEN = 3
    CMD_ADDR_START_REL = 3; CMD_ADDR_LEN = 4         # Command requests a 4-byte address
    CMD_PKTCNT_START_REL = 10; CMD_PKTCNT_LEN = 2

    ACK_HEADER_END_PATTERN = b'\x4D\xAA' # SAT ID + PCKT ID
    ACK_HEADER_END_START_REL = 16; ACK_HEADER_END_LEN = 2
    ACK_CMD_ECHO_START_REL = 18; ACK_CMD_ECHO_LEN = 11
    ACK_FOOTER_START_REL = 29; ACK_FOOTER_BYTE = b'\xAA'; ACK_FOOTER_LEN = 1

    # Downlink Data Packet Format fields relative to BYTE0_COL
    PACKET_ADDR_START_REL = 17; PACKET_ADDR_LEN = 4     # 4-byte Data Address / Offset
    PACKET_PAYLOAD_START_REL = 21; PACKET_PAYLOAD_MAX_LEN = 64 # byte[21] to byte[84]
    OFFSET_INCREMENT = 64 # Payload size determines offset increment

    PACKET_TIMEOUT_SECONDS = 5

    # --- Auto-detect Commands ---
    print(f"\nCSVファイル '{csv_path.name}' からダウンロードコマンド (tx=1, {CMD_PREFIX.hex().upper()}...) を検索中...")
    detected_commands = []
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            try: header = next(reader)
            except StopIteration: print("!! エラー: CSVが空です。"); return

            max_index_needed = BYTE0_COL + max(CMD_ADDR_START_REL + CMD_ADDR_LEN, CMD_PKTCNT_START_REL + CMD_PKTCNT_LEN) -1
            if len(header) <= max_index_needed:
                print(f"!! エラー: CSV列数が不足({len(header)})。コマンド解析に{max_index_needed+1}列必要。")
                return

            for row_num, row in enumerate(reader, start=2):
                if not row or len(row) <= TX_COL or row[TX_COL].strip() != '1': continue
                try:
                    if len(row) > BYTE0_COL + max(CMD_ADDR_START_REL + CMD_ADDR_LEN -1, CMD_PKTCNT_START_REL + CMD_PKTCNT_LEN -1):
                        cmd_prefix = parse_hex_bytes_from_row(row, BYTE0_COL + CMD_PREFIX_START_REL, CMD_PREFIX_LEN, row_num)
                        if cmd_prefix == CMD_PREFIX:
                            addr_bytes = parse_hex_bytes_from_row(row, BYTE0_COL + CMD_ADDR_START_REL, CMD_ADDR_LEN, row_num)
                            count_bytes = parse_hex_bytes_from_row(row, BYTE0_COL + CMD_PKTCNT_START_REL, CMD_PKTCNT_LEN, row_num)
                            ts_str = row[TS_COL].strip(); cmd_time = None
                            try: cmd_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
                            except ValueError:
                                try: cmd_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                                except ValueError: cmd_time = None

                            if addr_bytes and count_bytes and cmd_time:
                                packet_count = struct.unpack('>H', count_bytes)[0]
                                if 0 < packet_count < 100000: # Sanity check
                                    detected_commands.append({
                                        "row_num": row_num, "time": cmd_time, "addr": addr_bytes,
                                        "count_raw": count_bytes, "count": packet_count,
                                        "full_row": row
                                    })
                                else: print(f"!! 警告 (行 {row_num}): 異常なパケット数 {packet_count}。")
                except struct.error as e: print(f"!! 警告 (行 {row_num}): パケット数変換エラー: {e}。")
                except Exception as e: print(f"!! 警告 (行 {row_num}): コマンド解析エラー: {e}。"); continue
    except FileNotFoundError: print(f"!! エラー: CSVファイル '{csv_path}' が見つかりません。"); return
    except Exception as e: print(f"!! エラー: CSV読込/コマンド検索中にエラー: {e}"); traceback.print_exc(); return

    if not detected_commands: print(" -> ダウンロードコマンドが見つかりませんでした。"); return

    # --- User Command Selection ---
    print(f"\n検出されたダウンロードコマンド ({len(detected_commands)}件):")
    for i, cmd in enumerate(detected_commands):
        addr_hex = cmd['addr'].hex().upper(); count = cmd['count']
        print(f"  {i+1}: {cmd['time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} (行 {cmd['row_num']}) - Addr={addr_hex}, Pkts={count}")
    selected_cmd_index = -1
    while True:
        try:
            choice = input(f"処理したいコマンドの番号 (1-{len(detected_commands)}) を入力してください: ").strip()
            selected_cmd_index = int(choice) - 1
            if 0 <= selected_cmd_index < len(detected_commands): break
            else: print(f"!! 1 から {len(detected_commands)} の間で入力してください。")
        except ValueError: print("!! 数値を入力してください。")

    selected_command = detected_commands[selected_cmd_index]
    command_time = selected_command['time']
    command_row_num = selected_command['row_num']
    # Use first 2 bytes of requested address to identify relevant data packets
    requested_data_type_prefix = selected_command['addr'][:2]
    requested_packet_count = selected_command['count']
    command_line_content = selected_command['full_row']
    print(f"\n -> 選択されたコマンド: {command_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, Addr={selected_command['addr'].hex().upper()}, Pkts={requested_packet_count}")
    print(f"   -> 関連データパケットの識別に使用するアドレスプレフィックス: {requested_data_type_prefix.hex().upper()}")

    # --- Get File Type and Output Name ---
    print("\n復元するファイルの種類を選択してください:")
    print("   1: JPG 画像"); print("   2: H24 動画"); print("   3: その他バイナリ (.bin)")
    file_choice = ''
    while file_choice not in ['1', '2', '3']:
        file_choice = input("番号を入力 (1, 2, or 3): ").strip()
        if file_choice not in ['1', '2', '3']: print("!! 無効な番号です。")
    if file_choice == '1': ext = '.jpg'
    elif file_choice == '2': ext = '.h264'
    else: ext = '.bin'

    base_filename = input(f"\n出力するファイル名（拡張子なし、{ext}が付きます）を入力してください: ").strip()
    if not base_filename:
        base_filename = f'cmd_ack_restored_{command_time.strftime("%Y%m%d_%H%M%S")}'
        print(f"-> ファイル名が未入力のため、デフォルト名 '{base_filename}' を使用します。")
    output_filename = base_filename + ext

    # --- Find ACK and Collect Data ---
    collected_packets: dict[int, bytes] = {} # {byte_offset: payload_bytes}
    ack_found_time = None; ack_row_num = -1
    last_packet_time = command_time
    processed_packet_count = 0
    selected_cmd_echo_bytes = None

    try:
        # Extract expected echo bytes from command row (bytes 0 to 10 relative to BYTE0_COL)
        selected_cmd_echo_bytes = parse_hex_bytes_from_row(command_line_content, BYTE0_COL + 0, ACK_CMD_ECHO_LEN, command_row_num)
        if not selected_cmd_echo_bytes:
            print(f"!! エラー: コマンド行 {command_row_num} からACK比較用のバイト列 ({ACK_CMD_ECHO_LEN}バイト) を抽出できませんでした。")
            return

        # Proceed with searching ACK and collecting data
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            try:
                for _ in range(command_row_num): next(reader) # Skip to after command row
            except StopIteration: print("!! エラー: CSV読み込み中に予期せずファイル終端に達しました。"); return

            # --- Search for ACK ---
            print(f" -> コマンド {command_row_num} 行以降でACKパケットを検索中...")
            ack_search_row_num = command_row_num
            ack_found = False
            for row in reader:
                ack_search_row_num += 1
                if not row or len(row) <= TX_COL or row[TX_COL].strip() != '0': continue
                try:
                    if len(row) > BYTE0_COL + ACK_FOOTER_START_REL:
                        header_end = parse_hex_bytes_from_row(row, BYTE0_COL + ACK_HEADER_END_START_REL, ACK_HEADER_END_LEN, ack_search_row_num)
                        echo_in_ack = parse_hex_bytes_from_row(row, BYTE0_COL + ACK_CMD_ECHO_START_REL, ACK_CMD_ECHO_LEN, ack_search_row_num)
                        footer = parse_hex_bytes_from_row(row, BYTE0_COL + ACK_FOOTER_START_REL, ACK_FOOTER_LEN, ack_search_row_num)
                        if (header_end == ACK_HEADER_END_PATTERN and
                            echo_in_ack == selected_cmd_echo_bytes and
                            footer == ACK_FOOTER_BYTE):
                            ts_str = row[TS_COL].strip()
                            try: ack_found_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
                            except ValueError:
                                try: ack_found_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                                except ValueError: ack_found_time = None
                            if ack_found_time:
                                print(f" -> ACKパケットを行 {ack_search_row_num} ({ack_found_time.strftime('%H:%M:%S.%f')[:-3]}) で発見。")
                                ack_row_num = ack_search_row_num; last_packet_time = ack_found_time; ack_found = True; break
                            else: print(f"!! 警告: ACKパケットを行 {ack_search_row_num} で見つけましたが、タイムスタンプを解析できません。")
                except Exception: continue

            if not ack_found: print("!! エラー: 対応するACKパケットが見つかりませんでした。データ収集を開始できません。"); return

            # --- Collect Data Packets after ACK ---
            print(f" -> ACK時刻以降の受信パケット (アドレス {requested_data_type_prefix.hex().upper()}...) を収集中...")
            data_collection_row_num = ack_row_num
            for row in reader:
                data_collection_row_num += 1
                if not row or len(row) <= TX_COL: continue
                try:
                    ts_str = row[TS_COL].strip(); current_time = None
                    try: current_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
                    except ValueError:
                        try: current_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError: continue

                    if current_time <= ack_found_time: continue

                    if current_time - last_packet_time > timedelta(seconds=PACKET_TIMEOUT_SECONDS):
                        print(f"   -> {PACKET_TIMEOUT_SECONDS}秒以上新しい関連パケットがないため、収集を終了します (タイムアウト)。"); break

                    if row[TX_COL].strip() == '1': # Check for next command
                        if len(row) > BYTE0_COL + CMD_PREFIX_LEN - 1:
                            cmd_prefix = parse_hex_bytes_from_row(row, BYTE0_COL + CMD_PREFIX_START_REL, CMD_PREFIX_LEN, data_collection_row_num)
                            if cmd_prefix == CMD_PREFIX:
                                print(f"   -> 新しいダウンロードコマンドを行 {data_collection_row_num} で検出したため、収集を終了します。"); break
                        continue

                    # Process received data packet (tx=0, check address prefix)
                    if row[TX_COL].strip() == '0':
                        # Check length for Data Packet header fields
                        if len(row) > BYTE0_COL + max(PACKET_ADDR_START_REL + PACKET_ADDR_LEN - 1, PACKET_PAYLOAD_START_REL):
                            # Read the full 4-byte address/offset field
                            packet_addr_offset_bytes = parse_hex_bytes_from_row(row, BYTE0_COL + PACKET_ADDR_START_REL, PACKET_ADDR_LEN, data_collection_row_num)

                            # Check if the prefix matches and we got the full 4 bytes
                            if packet_addr_offset_bytes is not None and len(packet_addr_offset_bytes) == PACKET_ADDR_LEN and packet_addr_offset_bytes.startswith(requested_data_type_prefix):
                                # Use the full 4 bytes as the byte offset (Big Endian)
                                byte_offset = int.from_bytes(packet_addr_offset_bytes, 'big')

                                # Extract payload (up to PACKET_PAYLOAD_MAX_LEN bytes)
                                payload = parse_hex_bytes_from_row(row, BYTE0_COL + PACKET_PAYLOAD_START_REL, PACKET_PAYLOAD_MAX_LEN, data_collection_row_num)

                                if payload:
                                    if byte_offset not in collected_packets:
                                        collected_packets[byte_offset] = payload
                                        processed_packet_count += 1
                                        last_packet_time = current_time
                                        if processed_packet_count % 100 == 0: print(f"   -> {processed_packet_count} パケット収集済み...")
                                    # else: pass # Ignore duplicates
                                # else: # No valid payload extracted
                                #    print(f"警告 (行 {data_collection_row_num}): データパケットですがペイロード抽出失敗。")

                except struct.error as e: print(f"!! 警告 (行 {data_collection_row_num}): オフセット変換エラー: {e}")
                except Exception as e: print(f"!! 警告 (行 {data_collection_row_num}): パケット処理エラー: {e}"); continue

            print(f"   -> パケット収集完了。合計 {len(collected_packets)} 個の一意なパケットを収集しました。")

    except FileNotFoundError: print(f"!! エラー: CSVファイル '{csv_path}' が見つかりません。"); return
    except Exception as e: print(f"!! エラー: CSV処理中に予期せぬエラーが発生しました: {e}"); traceback.print_exc(); return

    # --- Verify and Reconstruct Data ---
    if not collected_packets: print("!! エラー: 該当するデータパケットが見つかりませんでした。"); return

    print("\n -> 受信パケットを検証中...")
    sorted_offsets = sorted(collected_packets.keys())
    reconstructed_data = bytearray()
    missing_offsets = []; expected_offset = -1; actual_received_count = len(sorted_offsets)

    try:
        if sorted_offsets:
            # Initialize expected_offset with the first received offset
            expected_offset = sorted_offsets[0]
            print(f"   -> 最初の受信オフセット {expected_offset:#08x} を基準に検証開始")
            # Report if the first offset is not the one expected from the command address (if addr LSBs != 0)
            command_start_offset = int.from_bytes(selected_command['addr'], 'big')
            if expected_offset != command_start_offset:
                print(f"   -> 注意: コマンド要求アドレス {command_start_offset:#08x} と最初の受信オフセット {expected_offset:#08x} が異なります。")
                # Assume the first received offset is the true start for gap checking
                # List missing offsets from command_start_offset up to expected_offset? Maybe too verbose.

        for offset in sorted_offsets:
            if offset > expected_offset:
                num_missing = (offset - expected_offset) // OFFSET_INCREMENT
                for i in range(num_missing): missing_offsets.append(expected_offset + i * OFFSET_INCREMENT)
                print(f"   -> 欠損検出: オフセット {expected_offset:#08x} から {offset:#08x} の間に {num_missing} パケット欠損の可能性")
            elif offset < expected_offset:
                print(f"!! 警告: オフセット {offset:#08x} が期待値 {expected_offset:#08x} より小さいです。順序異常の可能性。")

            reconstructed_data.extend(collected_packets[offset])
            expected_offset = offset + OFFSET_INCREMENT # Expect next offset based on current packet

        # Check for missing packets at the end, relative to requested count and *command start address*
        if requested_packet_count > 0:
            command_start_offset = int.from_bytes(selected_command['addr'], 'big')
            # Calculate the byte offset *after* the last expected packet
            offset_after_last_expected = command_start_offset + requested_packet_count * OFFSET_INCREMENT
            if expected_offset < offset_after_last_expected and actual_received_count > 0: # Check end only if we received packets
                num_missing_at_end = (offset_after_last_expected - expected_offset) // OFFSET_INCREMENT
                if num_missing_at_end > 0:
                    last_received_offset = sorted_offsets[-1]
                    last_expected_req_offset = command_start_offset + (requested_packet_count - 1) * OFFSET_INCREMENT
                    print(f"   -> 欠損検出: 最後の受信オフセット {last_received_offset:#08x} 以降、要求された最後のパケット(Offset {last_expected_req_offset:#08x}) までに {num_missing_at_end} パケット欠損の可能性")
                    for i in range(num_missing_at_end): missing_offsets.append(expected_offset + i * OFFSET_INCREMENT)

    except IndexError: print("!! エラー: 受信パケットリストが空のため、検証/再構築をスキップします。"); return
    except Exception as e: print(f"!! エラー: データ再構築中にエラー: {e}"); traceback.print_exc(); return

    print("-" * 30); print("【検証結果】")
    print(f" - 要求されたパケット数: {requested_packet_count}")
    print(f" - 実際に受信したユニークパケット数: {actual_received_count}")
    if missing_offsets:
        print(f" - !!! {len(missing_offsets)} 個のパケット欠損（または未達）を検出しました !!!")
        display_limit = 10
        # Display missing byte offsets
        missing_display = [f"{offset:#08x}" for offset in missing_offsets[:display_limit]]
        print(f"   - 欠損バイトオフセット (最初の{display_limit}件まで): {', '.join(missing_display)}")
        if len(missing_offsets) > display_limit: print(f"   - ... 他 {len(missing_offsets) - display_limit} 件")
    else:
        if actual_received_count == requested_packet_count: print(" - パケット欠損は見つからず、要求数と受信数が一致しました。")
        # Handle case where timeout happened before all packets arrived but no sequence gaps found
        elif actual_received_count < requested_packet_count and expected_offset == command_start_offset + actual_received_count * OFFSET_INCREMENT:
            print(f" - パケットシーケンスに欠損はありませんでしたが、受信数({actual_received_count})が要求数({requested_packet_count})に達しませんでした（タイムアウトまたは送信中断の可能性）。")
        # Handle other discrepancies (e.g., received more than requested?)
        else:
            print(f" - パケットシーケンスに欠損はありませんでしたが、受信数({actual_received_count})と要求数({requested_packet_count})が一致しません。")

    print("-" * 30)

    # --- Ask to proceed and Save File ---
    proceed = 'y'
    if missing_offsets or actual_received_count != requested_packet_count:
        while True:
            proceed_input = input("注意: パケット欠損または要求数との不一致があります。復元を続行しますか？ (y/n): ").lower().strip()
            if proceed_input in ['y', 'n']: proceed = proceed_input; break
            print("!! y または n を入力してください。")

    if proceed == 'y':
        print(f"\n -> データを '{output_filename}' に保存します...")
        try:
            with open(output_filename, 'wb') as f: f.write(reconstructed_data)
            print(f"成功: '{output_filename}' を作成 ({len(reconstructed_data)} バイト)")
            if missing_offsets: print("   -> 注意: パケット欠損があるため、ファイルが破損している可能性があります。")
            elif actual_received_count < requested_packet_count: print("   -> 注意: 要求されたすべてのパケットを受信できていないため、ファイルが不完全である可能性があります。")
        except IOError as e: print(f"エラー: ファイル '{output_filename}' の保存に失敗しました: {e}")
        except Exception as e: print(f"!! エラー: ファイル保存中に予期せぬエラー: {e}")
    else: print(" -> 復元処理を中断しました。")
    print("\n--- 処理完了 ---")

# --- Main menu (No changes needed) ---
def main():
    print("="*40); print("SMFデータ 復元/比較ツール"); print("="*40)
    print("実行したい操作を選択してください:")
    print("   1: (手動入力) ファイル復元 または ステータス/エラーコード解読")
    print("   2: (手動入力) 2つのデータを比較する")
    print("   3: (CSV入力) CSVログファイルから時間範囲でデータを復元")
    print("   4: (CSV入力) CSVログからコマンド基準でデータを復元 (欠損チェックあり)")
    choice = ''
    while choice not in ['1', '2', '3', '4']:
        choice = input("番号を入力 (1, 2, 3, or 4): ").strip()
        if choice not in ['1', '2', '3', '4']: print("!! 無効な番号です。1, 2, 3, 4 のいずれかを入力してください。")
    try:
        if choice == '1': reconstruct_mode()
        elif choice == '2': compare_mode()
        elif choice == '3': reconstruct_from_csv()
        elif choice == '4': reconstruct_from_csv_command()
    except KeyboardInterrupt: print("\n** 処理が中断されました **")
    except Exception as e: print(f"\n!! 予期せぬエラーが発生しました: {e}"); traceback.print_exc()

if __name__ == "__main__":
    main()