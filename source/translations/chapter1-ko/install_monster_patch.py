import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SERIAL = "emulator-5558"
PKG = "com.exvius.memorial.korean"

# 1. Push Ver227_0xkPiwVI.dat to /data/local/tmp/
dat_path = ROOT / "artifacts/chapter1-ko/Ver227_0xkPiwVI.dat"
print("Pushing Ver227_0xkPiwVI.dat to device...")
subprocess.run(["adb", "-s", SERIAL, "push", str(dat_path), "/data/local/tmp/Ver227_0xkPiwVI.dat"], check=True)

# 2. Copy to target directories with root
sh_script = f"""
mkdir -p /data/data/{PKG}/files/localized_texts/en
mkdir -p /sdcard/Android/data/{PKG}/files/localized_texts/en
cp /data/local/tmp/Ver227_0xkPiwVI.dat /data/data/{PKG}/files/localized_texts/en/Ver227_0xkPiwVI.dat
cp /data/local/tmp/Ver227_0xkPiwVI.dat /sdcard/Android/data/{PKG}/files/localized_texts/en/Ver227_0xkPiwVI.dat

OWNER=$(stat -c '%u:%g' /data/data/{PKG}/files)
chown -R $OWNER /data/data/{PKG}/files/localized_texts
chmod 644 /data/data/{PKG}/files/localized_texts/en/Ver227_0xkPiwVI.dat
chmod 644 /sdcard/Android/data/{PKG}/files/localized_texts/en/Ver227_0xkPiwVI.dat
echo "Installed Ver227_0xkPiwVI.dat to files and sdcard!"
"""

subprocess.run(["adb", "-s", SERIAL, "shell", f"su 0 sh -c \"{sh_script}\""], check=True)

# 3. Update gamedata.xml
print("Updating gamedata.xml with keyF_TEXT_MONSTER_NAME=227...")
xml_raw = subprocess.check_output(["adb", "-s", SERIAL, "shell", f"su 0 cat /data/data/{PKG}/shared_prefs/gamedata.xml"])
root = ET.fromstring(xml_raw)

# Check if keyF_TEXT_MONSTER_NAME already exists
node = None
for child in root:
    if child.get("name") == "keyF_TEXT_MONSTER_NAME":
        node = child
        break

if node is None:
    node = ET.SubElement(root, "string", {"name": "keyF_TEXT_MONSTER_NAME"})

node.text = "227"

staging_xml = ROOT / "artifacts/chapter1-ko/updated_gamedata.xml"
ET.ElementTree(root).write(str(staging_xml), encoding="utf-8", xml_declaration=True)

subprocess.run(["adb", "-s", SERIAL, "push", str(staging_xml), "/data/local/tmp/gamedata.xml"], check=True)
update_pref_sh = f"""
cp /data/local/tmp/gamedata.xml /data/data/{PKG}/shared_prefs/gamedata.xml
OWNER=$(stat -c '%u:%g' /data/data/{PKG}/shared_prefs)
chown $OWNER /data/data/{PKG}/shared_prefs/gamedata.xml
chmod 660 /data/data/{PKG}/shared_prefs/gamedata.xml
echo "Updated shared_prefs/gamedata.xml!"
"""
subprocess.run(["adb", "-s", SERIAL, "shell", f"su 0 sh -c \"{update_pref_sh}\""], check=True)

# 4. Restart the app cleanly
print("Restarting app...")
subprocess.run(["adb", "-s", SERIAL, "shell", f"am force-stop {PKG}"], check=True)
subprocess.run(["adb", "-s", SERIAL, "shell", f"am start -n {PKG}/com.square_enix.ffbejpn.Lapis"], check=True)
print("Done! App restarted.")
