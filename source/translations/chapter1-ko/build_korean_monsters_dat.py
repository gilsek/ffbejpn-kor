import sys
import csv
import base64
import zipfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT / "upstream/source/server"))
from ffbe_crypto import key16

KEY = "UOz3hI2k"
ZIP_PATH = ROOT / "downloads/release-2026.11.04.9/exvius-kira-r7.zip"
CSV_PATH = ROOT / "artifacts/chapter1-ko/csv_exports/chapter1_monsters.csv"

# Load monster translations from CSV: en -> ko, and monster_id -> ko
en_to_ko = {}
id_to_ko = {}

with open(CSV_PATH, "r", encoding="utf-8-sig") as fp:
    reader = csv.reader(fp)
    next(reader)
    for r in reader:
        # id, monster_id, base_id, area, jp, en, ko
        mid = r[1]
        en = r[5].strip()
        ko = r[6].strip()
        if en and ko:
            en_to_ko[en] = ko
        if mid and ko:
            id_to_ko[f"MST_MONSTER_NAME_{mid}"] = ko

# Ensure Steel Bat
en_to_ko["Steel Bat"] = "스틸 배트"

print(f"Loaded {len(en_to_ko)} EN->KO monster names and {len(id_to_ko)} ID->KO mappings.")

print("Reading Ver227_0xkPiwVI.dat from release archive...")
with zipfile.ZipFile(ZIP_PATH) as z:
    raw_encrypted = z.read("native/localized_texts/en/Ver227_0xkPiwVI.dat").decode("ascii")

cipher = Cipher(algorithms.AES(key16(KEY)), modes.ECB())
lines_encrypted = [l for l in raw_encrypted.splitlines() if l.strip()]

output_encrypted = []
replaced_count = 0

for encrypted in lines_encrypted:
    decryptor = cipher.decryptor()
    plain = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    layers = 0
    while plain and 1 <= plain[-1] <= 16 and plain[-plain[-1]:] == bytes([plain[-1]]) * plain[-1]:
        plain = plain[:-plain[-1]]
        layers += 1
    
    text_lines = plain.decode("utf-8").splitlines(keepends=True)
    for idx, line in enumerate(text_lines):
        fields = line.rstrip("\r\n").split("^")
        key_id = fields[0] # e.g. MST_MONSTER_NAME_102001000
        ending = line[len(line.rstrip("\r\n")):]
        
        ko_name = None
        if key_id in id_to_ko:
            ko_name = id_to_ko[key_id]
        elif len(fields) > 1 and fields[1] in en_to_ko:
            ko_name = en_to_ko[fields[1]]
        elif len(fields) > 1 and "Steel Bat" in fields[1]:
            ko_name = "스틸 배트"
            
        if ko_name:
            fields = [fields[0]] + [ko_name] * (len(fields) - 1)
            text_lines[idx] = "^".join(fields) + ending
            replaced_count += 1

    re_plain = "".join(text_lines).encode("utf-8")
    for _ in range(layers):
        pad = 16 - len(re_plain) % 16
        re_plain += bytes([pad]) * pad
    
    encryptor = cipher.encryptor()
    enc_bytes = encryptor.update(re_plain) + encryptor.finalize()
    output_encrypted.append(base64.b64encode(enc_bytes).decode("ascii"))

out_dat_path = ROOT / "artifacts/chapter1-ko/Ver227_0xkPiwVI.dat"
out_dat_path.write_text("\n".join(output_encrypted) + "\n", encoding="ascii")
print(f"Successfully repacked {out_dat_path.name}! Replaced {replaced_count} monster entries.")
