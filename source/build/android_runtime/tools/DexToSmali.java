import java.io.File;
import java.io.FileOutputStream;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import com.android.tools.smali.dexlib2.dexbacked.DexBackedDexFile;
import com.android.tools.smali.dexlib2.dexbacked.ZipDexContainer;

import brut.androlib.smali.SmaliDecoder;

/**
 * dex -> smali using the smali/dexlib2 classes already bundled in apktool_3.0.3.jar.
 * apktool 3.x ships no baksmali CLI entry point, so this tiny front end drives SmaliDecoder directly
 * (the same code path apktool uses when it decodes an APK).
 *
 * usage: java -cp "apktool_3.0.3.jar;this-classes" DexToSmali <classes.dex> <output-dir>
 */
public final class DexToSmali {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("usage: DexToSmali <classes.dex> <outDir>");
        File zip = File.createTempFile("dexsmali", ".zip");
        try {
            try (ZipOutputStream out = new ZipOutputStream(new FileOutputStream(zip))) {
                out.putNextEntry(new ZipEntry("classes.dex"));
                out.write(java.nio.file.Files.readAllBytes(new File(args[0]).toPath()));
                out.closeEntry();
            }
            ZipDexContainer container = new ZipDexContainer(zip);
            DexBackedDexFile dex = (DexBackedDexFile) container.getEntries().get("classes.dex");
            if (dex == null) {
                for (Object value : container.getEntries().values()) {
                    dex = (DexBackedDexFile) value;
                    break;
                }
            }
            if (dex == null) throw new IllegalStateException("No dex entry in " + args[0]);
            new SmaliDecoder(zip, true).decodeFile(dex, new File(args[1]));
        } finally {
            zip.delete();
        }
    }
}
