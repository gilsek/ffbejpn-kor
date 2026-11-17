package com.exvius.local;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Foreground service (type dataSync) that keeps the first download running while the screen is off.
 * All state lives in {@link DataUpdates}; this class only owns the notification, thread and wake locks.
 */
public final class DataDownloadService extends Service {
    static final String ACTION_RUN = "com.exvius.local.action.RUN";
    static final String EXTRA_MANDATORY = "mandatory";
    static final String EXTRA_REPAIR = "repair";

    private static final String CHANNEL_ID = "exvius_download";
    private static final int NOTIFICATION_ID = 7301;

    private static volatile DataDownloadService active;
    private PowerManager.WakeLock wakeLock;
    private WifiManager.WifiLock wifiLock;

    @Override public void onCreate() {
        super.onCreate();
        active = this;
    }

    @Override public int onStartCommand(Intent intent, int flags, final int startId) {
        try {
            createChannel();
            startForegroundCompat(build("게임 데이터를 준비하는 중...", 0, 0));
        } catch (RuntimeException error) {
            // e.g. ForegroundServiceStartNotAllowedException: still run, just without the foreground promotion.
        }
        if (!DataUpdates.working()) {
            stopSelf();
            return START_NOT_STICKY;
        }
        boolean mandatory = intent != null && intent.getBooleanExtra(EXTRA_MANDATORY, false);
        boolean repair = intent != null && intent.getBooleanExtra(EXTRA_REPAIR, false);
        acquireLocks();
        Thread worker = new Thread(new Runnable() {
            public void run() {
                try {
                    DataUpdates.run(DataDownloadService.this, mandatory, repair);
                } finally {
                    stopSelf(startId);
                }
            }
        }, "ExviusDataDownload");
        worker.start();
        return START_NOT_STICKY;
    }

    private void startForegroundCompat(Notification notification) {
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager == null) return;
        NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "게임 데이터 다운로드",
            NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("첫 실행 때 게임 데이터를 내려받는 동안 표시됩니다.");
        manager.createNotificationChannel(channel);
    }

    private Notification build(String message, long done, long total) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26 ?
            new Notification.Builder(this, CHANNEL_ID) : new Notification.Builder(this);
        builder.setContentTitle("Exvius KR")
            .setContentText(message)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setOngoing(true)
            .setOnlyAlertOnce(true);
        if (total > 0) builder.setProgress(1000, (int) Math.min(1000L, done * 1000L / total), false);
        else builder.setProgress(0, 0, true);
        return builder.build();
    }

    /** Called from DataUpdates.progress() on the download thread (or from the activity thread). */
    static void updateProgress(String message, long done, long total) {
        DataDownloadService service = active;
        if (service == null) return;
        try {
            NotificationManager manager = (NotificationManager) service.getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager != null) manager.notify(NOTIFICATION_ID, service.build(message, done, total));
        } catch (RuntimeException ignored) {
            // a notification update must never abort the transfer
        }
    }

    private void acquireLocks() {
        try {
            if (wakeLock == null) {
                PowerManager power = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (power != null) {
                    wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Exvius:download");
                    wakeLock.setReferenceCounted(false);
                }
            }
            if (wakeLock != null && !wakeLock.isHeld()) wakeLock.acquire();
        } catch (RuntimeException ignored) { }
        try {
            if (wifiLock == null) {
                WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
                if (wifi != null) wifiLock = wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "Exvius:download");
            }
            if (wifiLock != null && !wifiLock.isHeld()) wifiLock.acquire();
        } catch (RuntimeException ignored) { }
    }

    @Override public void onDestroy() {
        active = null;
        releaseLocks();
        super.onDestroy();
    }

    private void releaseLocks() {
        try { if (wakeLock != null && wakeLock.isHeld()) wakeLock.release(); } catch (RuntimeException ignored) { }
        try { if (wifiLock != null && wifiLock.isHeld()) wifiLock.release(); } catch (RuntimeException ignored) { }
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
