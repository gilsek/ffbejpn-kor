package com.exvius.local;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.Build;
import android.os.Bundle;
import android.os.StatFs;
import android.provider.Settings;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.ref.WeakReference;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Iterator;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * First complete download, cached offline play, and static release updates.
 *
 * The transfer itself runs in {@link DataDownloadService} (a foreground service in the same process);
 * this class keeps the state, manifest validation and install logic and is what the activity talks to.
 * GitHub releases redirect to objects.githubusercontent.com, so the HTTP layer follows redirects itself
 * and resumes a partial file with a Range request.
 */
public final class DataUpdates {
    // Release manifest / release asset prefix. build/jp_offline_build.py rewrites these two lines for
    // local test builds (--manifest-url / --assets-prefix).
    private static final String LATEST = "https://raw.githubusercontent.com/gilsek/ffbejpn-kor/main/data/latest.json";
    private static final String ASSETS = "https://github.com/gilsek/ffbejpn-kor/releases/download/";

    private static final AtomicBoolean working = new AtomicBoolean();
    private static volatile Progress listener;
    // Release clean-install gate: the downloader writes installed.json. Dev data is copied with adb/run-as
    // (no installed.json), so jp_offline_build.py --release false compiles this to false to keep dev working.
    private static final boolean REQUIRE_INSTALLED = true;
    private static WeakReference<Activity> foreground = new WeakReference<Activity>(null);
    private static boolean initialized, gameOpened, permissionPrompted, installerShown;

    public interface Progress {
        void update(String message, long done, long total);
        void complete();
        void failed(String message);
    }

    private DataUpdates() {}

    static synchronized void initialize(Context context) {
        if (initialized) return;
        initialized = true;
        ((Application) context.getApplicationContext()).registerActivityLifecycleCallbacks(
            new Application.ActivityLifecycleCallbacks() {
                public void onActivityResumed(Activity activity) {
                    foreground = new WeakReference<Activity>(activity);
                    maybeInstall(activity);
                }
                public void onActivityPaused(Activity activity) {
                    if (foreground.get() == activity) foreground.clear();
                }
                public void onActivityCreated(Activity activity, Bundle state) {
                    if (activity.getClass().getName().equals("com.square_enix.ffbejpn.Lapis"))
                        gameOpened = true;
                }
                public void onActivityStarted(Activity activity) {}
                public void onActivityStopped(Activity activity) {}
                public void onActivitySaveInstanceState(Activity activity, Bundle state) {}
                public void onActivityDestroyed(Activity activity) {}
            });
    }

    static boolean working() { return working.get(); }

    private static File state(Context context, String name) {
        return new File(context.getFilesDir(), "exvius/data/" + name);
    }
    public static File dataRoot(Context context) { return state(context, "static"); }
    public static boolean gameOpened() { return gameOpened; }
    public static boolean hasPending(Context context) { return state(context, "pending.json").isFile(); }
    public static boolean clientAssetsMissing(Context context) { return false; }
    public static boolean ready(Context context) {
        return (!REQUIRE_INSTALLED || state(context, "installed.json").isFile()) &&
            new File(dataRoot(context), "mst_decoded/F_UNIT_MST.ndjson").isFile();
    }
    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences("offline_updates", Context.MODE_PRIVATE);
    }
    private static boolean online(Context context) {
        ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) return false;
        if (Build.VERSION.SDK_INT >= 23) {
            android.net.Network network = manager.getActiveNetwork();
            if (network == null) return false;
            android.net.NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
            return capabilities != null && capabilities.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET);
        }
        NetworkInfo info = manager.getActiveNetworkInfo();
        return info != null && info.isConnected();
    }
    private static int appVersion(Context context) throws Exception {
        return context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionCode;
    }
    private static String read(File file) throws IOException {
        if (file.length() > 524288) throw new IOException("Update information is too large");
        try (FileInputStream input = new FileInputStream(file);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > 524288) throw new IOException("Update information is too large");
                output.write(buffer, 0, count);
            }
            return new String(output.toByteArray(), StandardCharsets.UTF_8);
        }
    }
    private static void write(File file, String text) throws IOException {
        File parent = file.getParentFile();
        if (!parent.isDirectory() && !parent.mkdirs()) throw new IOException("Cannot create update folder");
        File partial = new File(parent, file.getName() + ".new");
        try (FileOutputStream output = new FileOutputStream(partial)) {
            output.write(text.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
        try {
            android.system.Os.rename(partial.getPath(), file.getPath());
        } catch (android.system.ErrnoException error) {
            throw new IOException("Cannot save update information", error);
        }
    }
    private static JSONObject installed(Context context) throws Exception {
        File file = state(context, "installed.json");
        return file.isFile() ? new JSONObject(read(file)) : new JSONObject();
    }
    private static boolean installedPack(JSONObject current, JSONObject pack) throws Exception {
        JSONArray packs = current.optJSONArray("packs");
        if (packs == null) return false;
        for (int i = 0; i < packs.length(); i++) {
            JSONObject row = packs.getJSONObject(i);
            if (pack.getString("id").equals(row.optString("id")) &&
                pack.getString("sha256").equals(row.optString("sha256"))) return true;
        }
        return false;
    }
    private static void validate(JSONObject manifest) throws Exception {
        if (manifest.getInt("schema") != 1 || manifest.getLong("revision") < 1)
            throw new IOException("Unsupported update information");
        JSONArray packs = manifest.getJSONArray("packs");
        if (packs.length() < 1 || packs.length() > 1000) throw new IOException("Invalid data pack list");
        HashSet<String> ids = new HashSet<String>();
        for (int i = 0; i < packs.length(); i++) {
            JSONObject pack = packs.getJSONObject(i);
            if (!pack.getString("id").matches("[a-zA-Z0-9_-]{1,80}") || !ids.add(pack.getString("id")) ||
                !pack.getString("url").startsWith(ASSETS) ||
                !pack.getString("sha256").matches("[a-f0-9]{64}") ||
                pack.getLong("size") < 1 || pack.getLong("size") >= 2147483648L ||
                pack.getLong("unpackedSize") < 1)
                throw new IOException("Invalid data pack information");
        }
    }

    // ---------------------------------------------------------------- download storage

    private static File downloadFolder(Context context) throws IOException {
        File folder = new File(context.getFilesDir(), "exvius/updates");
        if (!folder.isDirectory() && !folder.mkdirs()) throw new IOException("Download storage is unavailable");
        return folder;
    }
    private static File downloadFile(Context context, String key, String suffix) throws IOException {
        return new File(downloadFolder(context), key + suffix);
    }
    static void progress(String text, long done, long total) {
        Progress current = listener;
        if (current != null) current.update(text, done, total);
        DataDownloadService.updateProgress(text, done, total);
    }

    /** Usable bytes under getFilesDir(), API 18+ (JP minSdk 21). */
    private static long availableBytes(Context context) {
        StatFs stat = new StatFs(context.getFilesDir().getPath());
        return stat.getAvailableBytes();
    }
    private static void ensureSpace(Context context, long packSize, long remainingUnpacked) throws IOException {
        long needed = packSize + remainingUnpacked;
        long available = availableBytes(context);
        if (available < needed)
            throw new IOException("남은 저장 공간이 부족합니다. " + (needed / 1048576) + "MB 이상 필요하지만 여유 공간은 "
                + (available / 1048576) + "MB입니다.");
    }

    // ---------------------------------------------------------------- HTTP transfer (in process)

    private static HttpURLConnection open(String address, long range) throws IOException {
        URL url = new URL(address);
        for (int redirect = 0; redirect < 6; redirect++) {
            HttpURLConnection connection = (HttpURLConnection) url.openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(30000);
            connection.setReadTimeout(60000);
            connection.setRequestProperty("User-Agent", "ExviusOfflineKR/0.1.0");
            if (range > 0) connection.setRequestProperty("Range", "bytes=" + range + "-");
            int code = connection.getResponseCode();
            if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308) {
                String location = connection.getHeaderField("Location");
                connection.disconnect();
                if (location == null) throw new IOException("Redirect without an address");
                url = new URL(url, location);
                continue;
            }
            return connection;
        }
        throw new IOException("Too many redirects");
    }

    /** One transfer attempt. Resumes part when possible; the caller retries with backoff. */
    private static void transfer(String address, File part, long expected, long base, long total, boolean small)
            throws IOException {
        long existing = part.isFile() ? part.length() : 0;
        if (small) {
            existing = 0;
            if (part.exists() && !part.delete()) throw new IOException("Cannot restart download");
        }
        if (expected > 0 && existing == expected) return;
        HttpURLConnection connection = open(address, existing);
        try {
            int code = connection.getResponseCode();
            boolean append;
            if (code == 206 && existing > 0) {
                append = true;
            } else if (code == 200) {
                existing = 0;
                append = false;
            } else {
                throw new IOException("Server replied with HTTP " + code);
            }
            try (InputStream input = connection.getInputStream();
                 FileOutputStream output = new FileOutputStream(part, append)) {
                byte[] buffer = new byte[131072];
                long done = existing;
                long reported = existing >> 20;
                int count;
                while ((count = input.read(buffer)) != -1) {
                    output.write(buffer, 0, count);
                    done += count;
                    if (expected > 0 && done > expected) throw new IOException("Download is larger than expected");
                    long block = done >> 20;
                    if (block != reported || (expected > 0 && done == expected)) {
                        reported = block;
                        progress(small ? "게임 데이터를 확인하는 중..." :
                            "게임 데이터를 내려받는 중: " + ((base + done) / 1048576) + " / " + (total / 1048576) + " MB",
                            base + done, total);
                    }
                }
                output.getFD().sync();
                // A connection that closes early is resumable: keep the .part and let the retry continue it.
                if (expected > 0 && done < expected) throw new IOException("Connection ended early");
            }
        } finally {
            connection.disconnect();
        }
    }

    /** Download a file into files/exvius/updates, resuming a .part file and retrying three times. */
    private static File download(Context context, String key, String url, String suffix, long expected,
                                 long base, long total, boolean small) throws Exception {
        File target = downloadFile(context, key, suffix);
        File part = new File(target.getParentFile(), target.getName() + ".part");
        if (expected > 0 && target.isFile() && target.length() == expected) return target;
        if (expected > 0 && part.isFile() && part.length() > expected && !part.delete())
            throw new IOException("Cannot restart download");
        Exception last = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            if (attempt > 0) Thread.sleep(2000L << (attempt - 1));   // 2s, 4s
            try {
                transfer(url, part, expected, base, total, small);
                last = null;
                break;
            } catch (Exception error) {
                last = error;
            }
        }
        if (last != null) throw new IOException(last.getMessage() == null ?
            "다운로드에 실패했습니다. 연결을 확인하고 다시 시도해 주세요." : last.getMessage(), last);
        if (expected > 0 && part.length() != expected) {
            if (part.length() > expected) part.delete();   // a short .part is kept for the next resume
            throw new IOException("받은 파일 크기가 올바르지 않습니다. 다시 시도해 주세요.");
        }
        if (target.exists() && !target.delete()) throw new IOException("Cannot replace the downloaded file");
        try {
            android.system.Os.rename(part.getPath(), target.getPath());
        } catch (android.system.ErrnoException error) {
            throw new IOException("Cannot finish the download", error);
        }
        return target;
    }

    private static File verifiedPack(Context context, JSONObject pack, long base, long total) throws Exception {
        String hash = pack.getString("sha256"), key = "data_" + hash;
        File file = download(context, key, pack.getString("url"), ".zip", pack.getLong("size"), base, total, false);
        File verified = downloadFile(context, key, ".verified");
        if (file.length() != pack.getLong("size")) {
            clearDownload(context, key, ".zip");
            throw new IOException("Downloaded file has the wrong size. Please retry.");
        }
        if (!verified.isFile() || !read(verified).equals(hash)) {
            progress("받은 게임 데이터를 확인하는 중...", base, total);
            if (!DataPack.sha256(file).equals(hash)) {
                clearDownload(context, key, ".zip");
                verified.delete();
                throw new IOException("게임 데이터 검증에 실패했습니다. 다시 시도해 주세요.");
            }
            write(verified, hash);
        }
        return file;
    }
    private static void clearDownload(Context context, String key, String suffix) throws Exception {
        preferences(context).edit().remove("download_" + key).commit();
        downloadFile(context, key, suffix).delete();
        downloadFile(context, key, ".verified").delete();
        File part = new File(downloadFolder(context), key + suffix + ".part");
        part.delete();
    }

    // ---------------------------------------------------------------- install

    private static long unpackedFrom(JSONArray packs, JSONObject current, int from) throws Exception {
        long sum = 0;
        for (int i = from; i < packs.length(); i++) {
            JSONObject pack = packs.getJSONObject(i);
            if (!installedPack(current, pack)) sum += pack.getLong("unpackedSize");
        }
        return sum;
    }

    private static void installPending(Context context, boolean repairAssets) throws Exception {
        JSONObject manifest = new JSONObject(read(state(context, "pending.json")));
        validate(manifest);
        JSONObject current = installed(context);
        JSONArray packs = manifest.getJSONArray("packs");
        File journalFile = state(context, "install-progress.json");
        JSONObject journal = journalFile.isFile() ? new JSONObject(read(journalFile)) : new JSONObject();
        JSONArray completed = journal.optLong("revision") == manifest.getLong("revision") ?
            journal.optJSONArray("completed") : null;
        if (completed == null) completed = new JSONArray();
        HashSet<String> installedHashes = new HashSet<String>();
        for (int i = 0; i < completed.length(); i++) installedHashes.add(completed.getString(i));
        long total = 0, transferred = 0;
        for (int i = 0; i < packs.length(); i++) total += packs.getJSONObject(i).getLong("size");
        for (int i = 0; i < packs.length(); i++) {
            JSONObject pack = packs.getJSONObject(i);
            boolean forcePack = repairAssets && pack.getString("id").equals("client-assets");
            if (!forcePack && (installedPack(current, pack) || installedHashes.contains(pack.getString("sha256")))) {
                transferred += pack.getLong("size");
                continue;
            }
            // Peak use is this zip plus the unpacked size of this and every later pack.
            ensureSpace(context, pack.getLong("size"), unpackedFrom(packs, current, i));
            File archive = downloadFile(context, "data_" + pack.getString("sha256"), ".zip");
            File verified = downloadFile(context, "data_" + pack.getString("sha256"), ".verified");
            if (!archive.isFile() || archive.length() != pack.getLong("size") || !verified.isFile() ||
                !read(verified).equals(pack.getString("sha256"))) {
                if (!archive.isFile() && !online(context))
                    throw new IOException("게임 데이터 설치를 마치려면 인터넷에 연결해 주세요.");
                archive = verifiedPack(context, pack, transferred, total);
            }
            progress("게임 데이터를 설치하는 중 (" + (i + 1) + "/" + packs.length() + ")...", i, packs.length());
            try {
                DataPack.extract(archive, context.getFilesDir(), pack.getLong("unpackedSize"));
            } catch (java.util.zip.ZipException error) {
                // The verified archive is unreadable (storage corruption): fetch it again next time.
                clearDownload(context, "data_" + pack.getString("sha256"), ".zip");
                throw new IOException("게임 데이터 팩을 설치하지 못했습니다. 다시 시도해 주세요.", error);
            } catch (IOException error) {
                // Keep the verified archive (no 1.4GB re-download for a full disk or a transient I/O error).
                throw new IOException("게임 데이터 팩을 설치하지 못했습니다. 저장 공간을 확인하고 다시 시도해 주세요.", error);
            }
            transferred += pack.getLong("size");
            completed.put(pack.getString("sha256"));
            journal.put("revision", manifest.getLong("revision")).put("completed", completed);
            write(journalFile, journal.toString());
            clearDownload(context, "data_" + pack.getString("sha256"), ".zip");
        }
        File registryFile = state(context, "registry.json");
        JSONObject registry = new JSONObject(read(registryFile));
        SharedPreferences.Editor registryEdit = context.getSharedPreferences("gamedata", Context.MODE_PRIVATE).edit();
        Iterator<String> keys = registry.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            if (!key.startsWith("keyF_")) throw new IOException("Invalid resource registry key");
            registryEdit.putString(key, registry.getString(key));
        }
        if (!registryEdit.commit()) throw new IOException("Cannot save game resource versions");
        if (!new File(dataRoot(context), "mst_decoded/F_UNIT_MST.ndjson").isFile())
            throw new IOException("The downloaded game data is incomplete");
        // Index files at files/ root belong to the old client data; a stale .i next to the Korean masters
        // is what makes the client read a truncated table and crash. Delete before marking installed so a
        // kill in between repeats this step.
        File[] leftovers = context.getFilesDir().listFiles();
        if (leftovers != null) {
            for (File file : leftovers) {
                if (file.isFile() && file.getName().endsWith(".i") && !file.delete())
                    throw new IOException("Cannot remove old index file " + file.getName());
            }
        }
        write(state(context, "installed.json"), manifest.toString());
        state(context, "pending.json").delete();
        journalFile.delete();
        for (int i = 0; i < packs.length(); i++)
            clearDownload(context, "data_" + packs.getJSONObject(i).getString("sha256"), ".zip");
    }

    // ---------------------------------------------------------------- public entry points

    public static void prepare(Context context, Progress progress, boolean repairAssets) {
        listener = progress;
        begin(context.getApplicationContext(), true, repairAssets);
    }
    public static void detach(Progress progress) { if (listener == progress) listener = null; }
    public static synchronized void checkInBackground(Context context) {
        listener = null;
        begin(context.getApplicationContext(), false, false);
    }
    private static void begin(Context context, boolean mandatory, boolean repairAssets) {
        if (!working.compareAndSet(false, true)) return;
        try {
            Intent intent = new Intent(context, DataDownloadService.class);
            intent.setAction(DataDownloadService.ACTION_RUN);
            intent.putExtra(DataDownloadService.EXTRA_MANDATORY, mandatory);
            intent.putExtra(DataDownloadService.EXTRA_REPAIR, repairAssets);
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
            else context.startService(intent);
        } catch (RuntimeException error) {
            working.set(false);
            Progress current = listener;
            if (mandatory && current != null)
                current.failed("게임 데이터를 내려받을 수 없습니다. 다시 시도해 주세요.");
        }
    }

    /** Runs the whole update in the foreground service thread. */
    static void run(Context context, boolean mandatory, boolean repairAssets) {
        try {
            if (repairAssets) {
                if (gameOpened) throw new IOException("게임을 닫았다가 다시 열어 주세요.");
                if (!online(context)) throw new IOException("게임 데이터를 복구하려면 인터넷에 연결해 주세요.");
                if (!hasPending(context)) {
                    File current = state(context, "installed.json");
                    File latest = current.isFile() ? current :
                        download(context, "latest", LATEST, ".json", -1, 0, 0, true);
                    write(state(context, "pending.json"), read(latest));
                    if (!current.isFile()) clearDownload(context, "latest", ".json");
                }
                installPending(context, true);
            } else if (hasPending(context)) {
                if (!mandatory || gameOpened) return;
                installPending(context, false);
            } else {
                if (!online(context)) throw new IOException("첫 게임 데이터 다운로드를 위해 인터넷에 연결해 주세요.");
                File latest = download(context, "latest", LATEST, ".json", -1, 0, 0, true);
                JSONObject manifest = new JSONObject(read(latest));
                validate(manifest);
                clearDownload(context, "latest", ".json");
                JSONObject current = installed(context);
                if (manifest.getInt("minAppVersionCode") <= appVersion(context) &&
                    (!ready(context) || manifest.getLong("revision") > current.optLong("revision"))) {
                    if (mandatory) {
                        // First installation needs space for only one downloaded part at a time.
                        write(state(context, "pending.json"), manifest.toString());
                        installPending(context, false);
                    } else {
                        JSONArray packs = manifest.getJSONArray("packs");
                        long total = 0, done = 0;
                        for (int i = 0; i < packs.length(); i++) {
                            JSONObject pack = packs.getJSONObject(i);
                            if (!installedPack(current, pack)) total += pack.getLong("size");
                        }
                        for (int i = 0; i < packs.length(); i++) {
                            JSONObject pack = packs.getJSONObject(i);
                            if (installedPack(current, pack)) continue;
                            verifiedPack(context, pack, done, total);
                            done += pack.getLong("size");
                        }
                        write(state(context, "pending.json"), manifest.toString());
                        // Running games keep their current files. Apply updates on the next launch.
                    }
                }
                JSONObject app = manifest.optJSONObject("app");
                if (app != null && app.optInt("versionCode") > appVersion(context))
                    downloadApp(context, app);
            }
            Progress current = listener;
            if (mandatory && ready(context) && current != null) current.complete();
            else if (mandatory && current != null) current.failed("앱 업데이트가 필요합니다. 설치한 뒤 다시 실행해 주세요.");
        } catch (Exception error) {
            android.util.Log.w("ExviusUpdates", "Update unavailable: " + error.getClass().getSimpleName());
            Progress current = listener;
            if (mandatory && current != null) current.failed(error.getMessage() == null ?
                "게임 데이터를 내려받지 못했습니다. 다시 시도해 주세요." : error.getMessage());
        } finally {
            listener = null;
            working.set(false);
        }
    }

    // ---------------------------------------------------------------- APK self-update

    private static void downloadApp(Context context, JSONObject app) throws Exception {
        String url = app.getString("url"), hash = app.getString("sha256");
        if (!url.startsWith(ASSETS) || !hash.matches("[a-f0-9]{64}")) throw new IOException("Invalid app update");
        File apk = download(context, "app_" + hash, url, ".apk", app.getLong("size"), 0, app.getLong("size"), false);
        if (apk.length() != app.getLong("size") || !DataPack.sha256(apk).equals(hash)) {
            clearDownload(context, "app_" + hash, ".apk");
            throw new IOException("App update verification failed");
        }
        preferences(context).edit().putString("pending_apk_path", apk.getAbsolutePath())
            .putInt("pending_apk_version", app.getInt("versionCode")).commit();
        Activity activity = foreground.get();
        if (activity != null) {
            final Activity target = activity;
            activity.runOnUiThread(new Runnable() {
                public void run() { maybeInstall(target); }
            });
        }
    }

    private static void maybeInstall(Activity activity) {
        try {
            SharedPreferences saved = preferences(activity);
            String path = saved.getString("pending_apk_path", null);
            if (path == null || activity.isFinishing() || installerShown) return;
            int version = saved.getInt("pending_apk_version", 0);
            File apk = new File(path);
            if (version <= appVersion(activity) || !apk.isFile()) {
                saved.edit().remove("pending_apk_path").remove("pending_apk_version").commit();
                return;
            }
            if (Build.VERSION.SDK_INT >= 26 && !activity.getPackageManager().canRequestPackageInstalls()) {
                if (!permissionPrompted) {
                    permissionPrompted = true;
                    activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        android.net.Uri.parse("package:" + activity.getPackageName())));
                }
                return;
            }
            // Internal storage cannot be shared with file://, so hand the APK to the system through our own
            // UpdateProvider (the JP APK's androidx FileProvider is obfuscated and cannot be called by name).
            android.net.Uri uri = UpdateProvider.uriFor(activity, apk);
            installerShown = true;
            activity.startActivity(new Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
        } catch (Exception error) {
            installerShown = false;
            android.util.Log.w("ExviusUpdates", "Android installer is unavailable: " + error);
        }
    }
}
