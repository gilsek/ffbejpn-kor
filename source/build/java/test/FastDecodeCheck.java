import com.exvius.jp.FastDecode;
import java.io.BufferedReader;
import java.io.FileReader;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * FastDecode 가 원본 LapisJNI(smali) 와 같은 결과를 내는지 실제 JP 마스터 파일로 비교한다.
 * usage: java -cp <out> FastDecodeCheck files.tsv   (각 줄: 경로 \t 키)
 * Orig* 는 smali 를 그대로 옮긴 것: 줄마다 Cipher, com.square_enix.ffbejpn.d.a(base64), LapisJNI.i(패딩).
 */
public class FastDecodeCheck {
    static final String IV = "dZMjkk8gFDzKHlsx";
    static final int[] B = new int[256];
    static {
        Arrays.fill(B, -1);
        char[] a = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".toCharArray();
        for (int i = 0; i < a.length; i++) B[a[i]] = i;
        B['='] = 0;
    }

    static byte[] origB64(String s) {               // d.a
        int len = s == null ? 0 : s.length();
        if (len == 0) return new byte[0];
        int bad = 0;
        for (int i = 0; i < len; i++) if (B[s.charAt(i)] < 0) bad++;
        int good = len - bad;
        if (good % 4 != 0) return null;
        int pad = 0;
        while (len > 1 && B[s.charAt(--len)] <= 0) if (s.charAt(len) == '=') pad++;
        int n = (good * 6 >> 3) - pad;
        byte[] out = new byte[n];
        for (int o = 0, p = 0; o < n; ) {
            int v = 0;
            for (int j = 0; j < 4; j++) {
                int c = B[s.charAt(p++)];
                if (c >= 0) v |= c << (18 - j * 6); else j--;
            }
            out[o++] = (byte) (v >> 16);
            if (o < n) { out[o++] = (byte) (v >> 8); if (o < n) out[o++] = (byte) v; }
        }
        return out;
    }

    static byte[] origI(byte[] b, int blk) {        // LapisJNI.i
        int n = b.length, p = b[n - 1];
        if (p > 0) { int r = (n - p) % blk; if (p != blk - r) return new byte[1]; }
        byte[] o = new byte[n - p];
        System.arraycopy(b, 0, o, 0, n - p);
        return o;
    }

    static String origLine(String s, String key, String iv) throws Exception {
        byte[] k = new byte[16], kb = key.getBytes("UTF-8");
        System.arraycopy(kb, 0, k, 0, Math.min(16, kb.length));
        Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
        c.init(2, new SecretKeySpec(k, "AES"), new IvParameterSpec(iv.getBytes("UTF-8")));
        return new String(origI(c.doFinal(origB64(s)), 16));
    }

    static String origFile(String path, String key, String iv) throws Exception {
        java.io.File f = new java.io.File(path);
        try (BufferedReader r = new BufferedReader(new FileReader(f))) {
            StringBuilder sb = new StringBuilder();
            int n = 0;
            for (String l; (l = r.readLine()) != null; n++) {
                if (n > 0) sb.append('\n');
                sb.append(origLine(l, key, iv));
            }
            return sb.toString();
        }
    }

    public static void main(String[] a) throws Exception {
        List<String> rows = Files.readAllLines(Paths.get(a[0]));
        int ok = 0, lines = 0;
        long tOrig = 0, tFast = 0;
        for (String row : rows) {
            if (row.isEmpty()) continue;
            String[] p = row.split("\t");
            long t0 = System.nanoTime();
            String o = origFile(p[0], p[1], IV);
            long t1 = System.nanoTime();
            String f = FastDecode.file(p[0], p[1], IV);
            long t2 = System.nanoTime();
            tOrig += t1 - t0; tFast += t2 - t1;
            if (!o.equals(f)) { System.out.println("DIFF " + p[0]); System.exit(1); }
            for (String l : Files.readAllLines(Paths.get(p[0]))) {
                if (!origLine(l, p[1], IV).equals(FastDecode.line(l, p[1], IV))) { System.out.println("LINE DIFF " + p[0]); System.exit(1); }
                lines++;
            }
            ok++;
        }
        System.out.printf("PASS files %d lines %d | orig %.0f ms, fast %.0f ms%n", ok, lines, tOrig / 1e6, tFast / 1e6);
    }
}
