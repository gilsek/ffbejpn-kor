package com.exvius.local;

import android.system.ErrnoException;
import android.system.Os;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Installs static game files without touching saves or application code. */
public final class DataPack {
    private DataPack() {}

    /**
     * Pack entry prefix -> destination folder, relative to getFilesDir(). This is the one place the
     * release layout is defined; the device experiment (2026-11-17) showed the JP client skips
     * CriFileInstaller::addLoadFile for files that already exist in files/, so original resources are
     * flattened straight into files/ (<name>.cpk, Ver*.dat) and the Korean masters replace them there.
     */
    private static final String DATA_PREFIX = "exvius/data/";
    private static final String UI_KO_PREFIX = "exvius/";
    private static final String RES_PREFIX = "";   // files/<basename>

    public static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[262144];
        try (InputStream input = new FileInputStream(file)) {
            int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        StringBuilder result = new StringBuilder(64);
        for (byte value : digest.digest()) result.append(String.format("%02x", value & 255));
        return result.toString();
    }

    public static File destination(File files, String name) throws IOException {
        if (name.indexOf('\\') >= 0 || name.startsWith("/") || name.contains("../"))
            throw new IOException("Invalid data pack path");
        String relative;
        if (name.startsWith("static/")) {
            relative = DATA_PREFIX + name;                                  // exvius/data/static/...
        } else if (name.equals("metadata/registry.json")) {
            relative = DATA_PREFIX + "registry.json";                       // exvius/data/registry.json
        } else if (name.startsWith("ui_ko/")) {
            relative = UI_KO_PREFIX + name;                                 // exvius/ui_ko/...
        } else if (name.startsWith("res/mst/") || name.startsWith("res/flat/")) {
            // JP original release resources: files/mst/<sub>/<name> and files/flat/<name> both end up as
            // files/<name>, matching the client's own destination for these (device check 2026-11-17).
            String base = name.substring(name.lastIndexOf('/') + 1);
            if (base.length() == 0) throw new IOException("Invalid data pack path");
            relative = RES_PREFIX + base;
        } else if ((name.startsWith("ffbe/mst_ko/") || name.startsWith("ffbe/flat_ko/"))
                && name.indexOf('/', 5) == name.lastIndexOf('/') && !name.endsWith("/")) {
            // Files the client requests as new downloads (bumped masters, stub scenes): jp_offline.js
            // localize() copies them from files/ffbe/{mst_ko,flat_ko}/, the dev layout (2026-11-17).
            relative = name;
        } else {
            throw new IOException("Unsupported data pack entry");
        }
        File root = files.getCanonicalFile(), target = new File(root, relative).getCanonicalFile();
        if (!target.getPath().startsWith(root.getPath() + File.separator))
            throw new IOException("Data pack path escapes game storage");
        return target;
    }

    public static void extract(File archive, File files, long expectedBytes) throws IOException {
        try (ZipFile zip = new ZipFile(archive)) {
            if (zip.size() > 100000) throw new IOException("Data pack has too many entries");
            Set<String> names = new HashSet<String>();
            Set<String> targets = new HashSet<String>();
            long declared = 0;
            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory()) continue;
                String path = destination(files, entry.getName()).getPath();
                // Flat resource layout: two different entries can name the same files/<name>.
                if (!names.add(entry.getName()) || !targets.add(path) || entry.getSize() < 0)
                    throw new IOException("Invalid data pack directory");
                declared = Math.addExact(declared, entry.getSize());
            }
            if (declared != expectedBytes) throw new IOException("Data pack size does not match");
            entries = zip.entries();
            byte[] buffer = new byte[262144];
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory()) continue;
                File target = destination(files, entry.getName()), parent = target.getParentFile();
                if (!parent.isDirectory() && !parent.mkdirs()) throw new IOException("Cannot create game folder");
                File partial = new File(parent, target.getName() + ".installing");
                long written = 0;
                try {
                    try (InputStream input = zip.getInputStream(entry);
                         FileOutputStream output = new FileOutputStream(partial)) {
                        int count;
                        while ((count = input.read(buffer)) != -1) {
                            written += count;
                            if (written > entry.getSize()) throw new IOException("Invalid expanded file size");
                            output.write(buffer, 0, count);
                        }
                    }
                    if (written != entry.getSize()) throw new IOException("Incomplete game file");
                    try {
                        Os.rename(partial.getPath(), target.getPath());
                    } catch (ErrnoException error) {
                        throw new IOException("Cannot finish installing game file", error);
                    }
                } finally {
                    if (partial.exists()) partial.delete();
                }
            }
        }
    }
}
