package com.exvius.jp;

import android.content.Context;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.OutputStreamWriter;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.FutureTask;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * LapisJNI.decodeCStringForBase64WithNewCrypto / decodeFileForBase64WithNewCrypto 의 같은 결과를 내는 빠른 판.
 * 원본은 마스터 한 줄마다 Cipher.getInstance + init 을 하고 base64 를 String.charAt 으로 푼다
 * (로그인 마스터 로딩 9.1초 중 복호화 약 5.3초, 2026-11-10 실측). 여기서는 키·IV가 같으면 Cipher 를 재사용한다.
 * - 키: key UTF-8 앞 16바이트(모자라면 0), AES/CBC/PKCS5Padding, IV: iv UTF-8
 * - base64: 표준 알파벳, 알파벳 밖 글자는 무시(원본 d.a 와 같음) = MIME 디코더
 * - 복호화 뒤 원본 LapisJNI.i(bytes, 16) 와 같은 패딩 한 겹 제거
 *
 * 미리 복호화(2026-11-10): 로그인 때 GL 스레드에서 100ms 넘게 걸린 파일(AbilityMst 39MB 0.58초 등)은
 * files/fastdecode_prefetch.txt 에 경로·키·IV를 적어 두고, 다음 실행부터 Lapis.onCreate 에서 prefetch() 가
 * 백그라운드 스레드로 미리 풀어 둔다. file() 은 같은 경로·키·IV·크기·수정시각이면 그 결과를 한 번 꺼내 쓴다.
 */
public final class FastDecode {
    private static final Base64.Decoder B64 = Base64.getMimeDecoder();
    private static final long SLOW_MS = 100;
    private static Cipher cipher;
    private static String cKey, cIv;

    private static File listFile;
    private static final Map<String, String[]> known = new LinkedHashMap<>();   // path -> {key, iv}
    private static final Map<String, Pre> pre = new HashMap<>();

    private static final class Pre {
        final String key, iv;
        final long len, mtime;
        final FutureTask<String> task;
        Pre(String path, String key, String iv) {
            File f = new File(path);
            this.key = key; this.iv = iv; this.len = f.length(); this.mtime = f.lastModified();
            this.task = new FutureTask<>(() -> {
                try { return decodeFile(path, newCipher(key, iv)); } catch (Throwable e) { return null; }
            });
        }
    }

    private FastDecode() {}

    private static Cipher newCipher(String key, String iv) throws Exception {
        byte[] k = new byte[16];
        byte[] kb = key.getBytes("UTF-8");
        System.arraycopy(kb, 0, k, 0, Math.min(16, kb.length));
        Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(k, "AES"), new IvParameterSpec(iv.getBytes("UTF-8")));
        return c;
    }

    private static Cipher cipher(String key, String iv) throws Exception {
        if (cipher == null || !key.equals(cKey) || !iv.equals(cIv)) {
            cipher = newCipher(key, iv); cKey = key; cIv = iv;
        }
        return cipher;
    }

    /** LapisJNI.i([BI) 와 같다. */
    private static byte[] unpad(byte[] b, int block) {
        int n = b.length;
        int p = b[n - 1];
        if (p > 0 && p != block - (n - p) % block) return new byte[1];
        byte[] out = new byte[n - p];
        System.arraycopy(b, 0, out, 0, n - p);
        return out;
    }

    private static String decodeLine(Cipher c, String s) throws Exception {
        return new String(unpad(c.doFinal(B64.decode(s)), 16));
    }

    public static synchronized String line(String s, String key, String iv) throws Exception {
        Cipher c = cipher(key, iv);
        try {
            return decodeLine(c, s);
        } catch (Exception e) {
            cipher = null;                 // 실패 뒤 상태를 믿지 않는다
            throw e;
        }
    }

    private static String decodeFile(String path, Cipher c) throws Exception {
        File f = new File(path);
        try (BufferedReader r = new BufferedReader(new FileReader(f))) {
            StringBuilder sb = new StringBuilder((int) (f.length() * 0.8f));
            int n = 0;
            for (String l; (l = r.readLine()) != null; n++) {
                if (n > 0) sb.append('\n');
                sb.append(decodeLine(c, l));
            }
            return sb.toString();
        }
    }

    public static String file(String path, String key, String iv) throws Exception {
        Pre p;
        synchronized (pre) { p = pre.remove(path); }
        if (p != null && p.key.equals(key) && p.iv.equals(iv)) {
            File f = new File(path);
            p.task.run();                  // 아직 차례가 안 왔으면 여기서 푼다(이미 도는 중이면 바로 돌아옴)
            String s = p.task.get();
            if (s != null && f.length() == p.len && f.lastModified() == p.mtime) return s;
        }
        long t = System.nanoTime();
        String s;
        synchronized (FastDecode.class) {
            Cipher c = cipher(key, iv);
            try {
                s = decodeFile(path, c);
            } catch (Exception e) {
                cipher = null;
                throw e;
            }
        }
        if ((System.nanoTime() - t) / 1000000 > SLOW_MS) remember(path, key, iv);
        return s;
    }

    private static void remember(String path, String key, String iv) {
        synchronized (known) {
            if (listFile == null) return;
            String[] old = known.get(path);
            if (old != null && old[0].equals(key) && old[1].equals(iv)) return;
            known.put(path, new String[] {key, iv});
            try (OutputStreamWriter w = new OutputStreamWriter(new FileOutputStream(listFile), "UTF-8")) {
                for (Map.Entry<String, String[]> e : known.entrySet())
                    w.write(e.getKey() + "\t" + e.getValue()[0] + "\t" + e.getValue()[1] + "\n");
            } catch (Throwable ignored) {
            }
        }
    }

    /** Lapis.onCreate 에서 부른다. 예외를 밖으로 내지 않는다. */
    public static void prefetch(Context ctx) {
        try {
            final List<Pre> tasks = new ArrayList<>();
            synchronized (known) {
                if (listFile != null) return;
                listFile = new File(ctx.getFilesDir(), "fastdecode_prefetch.txt");
                if (listFile.isFile()) {
                    try (BufferedReader r = new BufferedReader(new FileReader(listFile))) {
                        for (String l; (l = r.readLine()) != null; ) {
                            String[] a = l.split("\t");
                            if (a.length != 3 || !new File(a[0]).isFile()) continue;
                            known.put(a[0], new String[] {a[1], a[2]});
                            Pre p = new Pre(a[0], a[1], a[2]);
                            synchronized (pre) { pre.put(a[0], p); }
                            tasks.add(p);
                        }
                    }
                }
            }
            if (tasks.isEmpty()) return;
            Thread th = new Thread(() -> { for (Pre p : tasks) p.task.run(); }, "FastDecodePrefetch");
            th.setDaemon(true);
            th.setPriority(Thread.MIN_PRIORITY);
            th.start();
        } catch (Throwable ignored) {
        }
    }
}
