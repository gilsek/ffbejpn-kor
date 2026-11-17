import os

targets = [b'crash landing', b'flying monsters']

def scan_dir(base):
    for root, dirs, files in os.walk(base):
        for f in files:
            p = os.path.join(root, f)
            try:
                with open(p, 'rb') as fp:
                    data = fp.read()
                    for t in targets:
                        if t in data:
                            print("FOUND:", p, t)
            except Exception:
                pass

print("Scanning /data/data/com.exvius.memorial.korean ...")
scan_dir('/data/data/com.exvius.memorial.korean')
print("Scanning /sdcard/Android/data/com.exvius.memorial.korean ...")
scan_dir('/sdcard/Android/data/com.exvius.memorial.korean')
print("Scanning /data/app ...")
scan_dir('/data/app')
print("SCAN COMPLETE")
