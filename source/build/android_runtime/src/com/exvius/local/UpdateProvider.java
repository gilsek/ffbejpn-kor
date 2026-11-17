package com.exvius.local;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Read-only provider that hands a downloaded update APK to the Android installer.
 * The JP APK's androidx FileProvider is obfuscated (getUriForFile renamed), so reflection on it fails;
 * this class serves only plain file names directly under files/exvius/updates/ ending in ".apk".
 * URI: content://<package>.updates/<name>.apk
 */
public final class UpdateProvider extends ContentProvider {

    static Uri uriFor(android.content.Context context, File apk) {
        return Uri.parse("content://" + context.getPackageName() + ".updates/" + Uri.encode(apk.getName()));
    }

    private File resolve(Uri uri) throws FileNotFoundException {
        String name = uri.getLastPathSegment();
        if (name == null || !name.endsWith(".apk") || name.contains("/") || name.contains("\\")
                || name.startsWith(".") || uri.getPathSegments().size() != 1)
            throw new FileNotFoundException("Not an update APK");
        File folder = new File(getContext().getFilesDir(), "exvius/updates");
        File file = new File(folder, name);
        if (!file.isFile()) throw new FileNotFoundException(name);
        return file;
    }

    @Override public boolean onCreate() { return true; }

    @Override public String getType(Uri uri) { return "application/vnd.android.package-archive"; }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new SecurityException("Read only");
        return ParcelFileDescriptor.open(resolve(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        File file;
        try {
            file = resolve(uri);
        } catch (FileNotFoundException error) {
            return null;
        }
        MatrixCursor cursor = new MatrixCursor(new String[] {OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        cursor.addRow(new Object[] {file.getName(), file.length()});
        return cursor;
    }

    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) {
        throw new UnsupportedOperationException();
    }
}
