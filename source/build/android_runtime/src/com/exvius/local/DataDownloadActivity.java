package com.exvius.local;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

/** First-install data download; subsequent launches go straight to the game. */
public final class DataDownloadActivity extends Activity implements DataUpdates.Progress {
    private TextView status;
    private ProgressBar progress;
    private Button retry;
    private boolean repairAssets;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        DataUpdates.initialize(getApplicationContext());
        requestNotificationPermission();
        if (DataUpdates.ready(this) && (!DataUpdates.hasPending(this) || DataUpdates.gameOpened())) {
            openGame(true);
            return;
        }
        repairAssets = DataUpdates.clientAssetsMissing(this);
        showDownloadPage();
        DataUpdates.prepare(this, this, repairAssets);
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {"android.permission.POST_NOTIFICATIONS"}, 1);
        }
    }

    private void showDownloadPage() {
        if (status != null) return;
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setGravity(Gravity.CENTER);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        page.setPadding(padding, padding, padding, padding);
        TextView title = new TextView(this);
        title.setText("Exvius KR");
        title.setTextSize(28);
        title.setGravity(Gravity.CENTER);
        page.addView(title);
        status = new TextView(this);
        status.setText("게임 데이터를 내려받을 준비를 하고 있습니다.\n설치가 끝나면 오프라인으로 플레이할 수 있습니다.");
        status.setTextSize(17);
        status.setGravity(Gravity.CENTER);
        status.setPadding(0, padding, 0, padding);
        page.addView(status);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(1000);
        page.addView(progress, new LinearLayout.LayoutParams(-1, -2));
        retry = new Button(this);
        retry.setText("다시 시도");
        retry.setVisibility(View.GONE);
        retry.setOnClickListener(new View.OnClickListener() {
            public void onClick(View view) {
                retry.setVisibility(View.GONE);
                DataUpdates.prepare(DataDownloadActivity.this, DataDownloadActivity.this, repairAssets);
            }
        });
        page.addView(retry);
        setContentView(page);
    }

    private void openGame(boolean checkForUpdates) {
        if (checkForUpdates) DataUpdates.checkInBackground(this);
        Intent game = new Intent();
        game.setClassName(getPackageName(), "com.square_enix.ffbejpn.Lapis");
        startActivity(game);
        finish();
    }

    @Override public void onDestroy() {
        DataUpdates.detach(this);
        super.onDestroy();
    }

    @Override public void update(final String message, final long done, final long total) {
        runOnUiThread(new Runnable() {
            public void run() {
                if (isFinishing() || status == null) return;
                status.setText(message);
                progress.setIndeterminate(total <= 0);
                if (total > 0) progress.setProgress((int) Math.min(1000L, done * 1000L / total));
            }
        });
    }

    @Override public void complete() {
        runOnUiThread(new Runnable() {
            public void run() { if (!isFinishing()) openGame(false); }
        });
    }

    @Override public void failed(final String message) {
        runOnUiThread(new Runnable() {
            public void run() {
                if (isFinishing()) return;
                if (status == null) showDownloadPage();
                status.setText(message);
                progress.setIndeterminate(false);
                retry.setVisibility(View.VISIBLE);
            }
        });
    }
}
