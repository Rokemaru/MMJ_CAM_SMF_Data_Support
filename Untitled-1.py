from pathlib import Path

# Use a raw string so backslashes in the Windows path don't produce unicode escape errors
file_path = Path(r"C:\Users\32456\Desktop\SMF_Data_check\recovered_image.jpg")

try:
    data = file_path.read_bytes()
except FileNotFoundError:
    print(f"File not found: {file_path}")
    data = b""
except Exception as e:
    print(f"Error reading file {file_path}: {e}")
    data = b""

if data:
    first = data[:32].hex()
    last = data[-32:].hex()
else:
    first = ""
    last = ""

print("First 32 bytes:", first)
print("Last 32 bytes:", last)
