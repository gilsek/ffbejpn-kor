"""Read the last effective path from the locally verified release ZIPs."""
import json
import zipfile
from pathlib import Path


class Release:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.manifest = json.loads((self.folder / 'manifest.json').read_text())
        self.archives = {}
        self.files = {}
        for pack in self.manifest['packs']:
            archive = zipfile.ZipFile(self.folder / pack['url'].rsplit('/', 1)[-1])
            self.archives[pack['id']] = archive
            for entry in archive.infolist():
                if not entry.is_dir():
                    self.files[entry.filename] = (pack['id'], entry)

    def read(self, name):
        pack, entry = self.files[name]
        return self.archives[pack].read(entry)

    def table(self, name, text=False):
        folder = 'text_decoded' if text else 'mst_decoded'
        return [json.loads(line) for line in self.read(f'static/{folder}/{name}.ndjson').decode('utf8').splitlines() if line]

    def close(self):
        for archive in self.archives.values():
            archive.close()
