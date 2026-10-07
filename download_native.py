"""Adds real file downloads to the Android app (run by the build after "npx cap add android").

A web page inside an Android app cannot save a file by itself, so until now every "Download" opened the share
sheet. This adds a small plugin, SaveFile, that writes the file into the phone's own Downloads folder
(Download/Sangam360), where the Files app and every PDF reader find it:

  - Android 10 and newer: through the system's Downloads collection. No permission is asked.
  - Android 9 and older:  straight into the public Download folder. The storage permission is asked the first time.

native-bridge.js calls it for every download in the app (receipts, invoices, bills, documents, CSV exports) and
then shows "Downloaded · <name>" with an Open button. A "Download complete" notification is shown as well when
notifications are allowed.

"python3 download_native.py --remove" takes the plugin out again (the last fallback of the build): the app then
saves through the Filesystem plugin and, where that is not possible, through the share sheet as before.
If anything here does not match the Android project, it prints a note and leaves the project unchanged.
"""
import os, re, sys

MAIN = r'''package com.sangam360.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // "Download": saves files into the phone's Downloads folder
        registerPlugin(SaveFilePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
'''

PLUGIN = r'''package com.sangam360.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;

import androidx.core.content.FileProvider;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

/**
 * Called from the web app (native-bridge.js):
 *   SaveFile.save({ name, data (base64), mime })  ->  { uri, name, folder }   the file is in Download/Sangam360
 *   SaveFile.open({ uri, mime })                                              opens it in the phone's own viewer
 */
@CapacitorPlugin(
    name = "SaveFile",
    permissions = { @Permission(alias = "storage", strings = { Manifest.permission.WRITE_EXTERNAL_STORAGE }) }
)
public class SaveFilePlugin extends Plugin {

    private static final String FOLDER = "Sangam360";
    private static final String CH = "s360_downloads";
    private static int nextId = 7400;

    @PluginMethod
    public void save(PluginCall call) {
        // Android 9 and older write into the shared folder directly and need the storage permission for that
        if (Build.VERSION.SDK_INT < 29 && getPermissionState("storage") != PermissionState.GRANTED) {
            requestPermissionForAlias("storage", call, "storageAnswer");
            return;
        }
        write(call);
    }

    @PermissionCallback
    private void storageAnswer(PluginCall call) {
        if (getPermissionState("storage") == PermissionState.GRANTED) write(call);
        else call.reject("Storage permission was not given");
    }

    private static String clean(String name) {
        String n = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]+", "_").trim();
        while (n.startsWith(".")) n = n.substring(1);
        if (n.length() > 120) n = n.substring(n.length() - 120);
        return n.length() == 0 ? "download" : n;
    }

    /** "Receipt.pdf", then "Receipt (1).pdf", "Receipt (2).pdf" ... */
    private static File free(File dir, String name) {
        File f = new File(dir, name);
        if (!f.exists()) return f;
        int dot = name.lastIndexOf('.');
        String base = dot > 0 ? name.substring(0, dot) : name, ext = dot > 0 ? name.substring(dot) : "";
        for (int i = 1; i < 500; i++) {
            f = new File(dir, base + " (" + i + ")" + ext);
            if (!f.exists()) return f;
        }
        return new File(dir, base + " " + System.currentTimeMillis() + ext);
    }

    private void write(final PluginCall call) {
        final String name = clean(call.getString("name", "download"));
        final String mime0 = call.getString("mime", "");
        final String mime = mime0 == null || mime0.length() == 0 ? "application/octet-stream" : mime0;
        final String data = call.getString("data", "");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    byte[] bytes = Base64.decode(data == null ? "" : data, Base64.DEFAULT);
                    Context ctx = getContext();
                    Uri uri = null;
                    String shown = name;
                    if (Build.VERSION.SDK_INT >= 29) {
                        ContentResolver cr = ctx.getContentResolver();
                        ContentValues v = new ContentValues();
                        v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                        v.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                        v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + FOLDER);
                        v.put(MediaStore.MediaColumns.IS_PENDING, 1);
                        uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                        if (uri == null) throw new Exception("The file could not be created");
                        try {
                            OutputStream os = cr.openOutputStream(uri);
                            if (os == null) throw new Exception("The file could not be opened");
                            try { os.write(bytes); os.flush(); } finally { os.close(); }
                        } catch (Exception e) {
                            try { cr.delete(uri, null, null); } catch (Exception ignored) { }
                            throw e;
                        }
                        ContentValues ready = new ContentValues();
                        ready.put(MediaStore.MediaColumns.IS_PENDING, 0);
                        cr.update(uri, ready, null, null);
                        // the system adds " (1)" when a file with this name is already there: report the real name
                        Cursor c = null;
                        try {
                            c = cr.query(uri, new String[] { MediaStore.MediaColumns.DISPLAY_NAME }, null, null, null);
                            if (c != null && c.moveToFirst()) {
                                String real = c.getString(0);
                                if (real != null && real.length() > 0) shown = real;
                            }
                        } catch (Exception ignored) {
                        } finally {
                            if (c != null) c.close();
                        }
                    } else {
                        File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), FOLDER);
                        if (!dir.exists() && !dir.mkdirs() && !dir.exists()) throw new Exception("The Downloads folder could not be used");
                        File f = free(dir, name);
                        FileOutputStream os = new FileOutputStream(f);
                        try { os.write(bytes); os.flush(); } finally { os.close(); }
                        try { MediaScannerConnection.scanFile(ctx, new String[] { f.getAbsolutePath() }, new String[] { mime }, null); } catch (Exception ignored) { }
                        shown = f.getName();
                        // the file is saved; an address other apps can open it with is a bonus (for "Open")
                        try { uri = FileProvider.getUriForFile(ctx, ctx.getPackageName() + ".fileprovider", f); } catch (Exception ignored) { }
                    }
                    if (uri != null) announce(ctx, uri, mime, shown);
                    JSObject r = new JSObject();
                    r.put("uri", uri == null ? "" : uri.toString());
                    r.put("name", shown);
                    r.put("folder", "Download/" + FOLDER);
                    call.resolve(r);
                } catch (Exception e) {
                    call.reject("The file could not be saved: " + e.getMessage());
                }
            }
        }).start();
    }

    private static Intent viewer(Uri uri, String mime) {
        Intent i = new Intent(Intent.ACTION_VIEW);
        i.setDataAndType(uri, mime == null || mime.length() == 0 ? "*/*" : mime);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        return i;
    }

    @PluginMethod
    public void open(PluginCall call) {
        try {
            String uri = call.getString("uri", "");
            if (uri == null || uri.length() == 0) { call.reject("Nothing to open"); return; }
            getContext().startActivity(viewer(Uri.parse(uri), call.getString("mime", "")));
            call.resolve();
        } catch (Exception e) {
            call.reject("No app on this phone can open this file");
        }
    }

    /** "Download complete" in the notification bar; a tap opens the file. Skipped silently when notifications are off. */
    private void announce(Context ctx, Uri uri, String mime, String name) {
        try {
            if (Build.VERSION.SDK_INT >= 33 && ctx.checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) return;
            NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            if (Build.VERSION.SDK_INT >= 26) {
                nm.createNotificationChannel(new NotificationChannel(CH, "Downloads", NotificationManager.IMPORTANCE_LOW));
            }
            int id = nextId++;
            int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0);
            PendingIntent tap = PendingIntent.getActivity(ctx, id, viewer(uri, mime), flags);
            Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(ctx, CH) : new Notification.Builder(ctx);
            b.setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle(name)
                .setContentText("Download complete · tap to open")
                .setContentIntent(tap)
                .setAutoCancel(true);
            nm.notify(id, b.build());
        } catch (Exception ignored) {
        }
    }
}
'''

REG = "registerPlugin(SaveFilePlugin.class);"
PERM = '    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" android:maxSdkVersion="28" />\n'


def find_activity(root):
    for d, _, files in os.walk(os.path.join(root, "java")):
        if "MainActivity.java" in files:
            return os.path.join(d, "MainActivity.java")
    return None


def remove(root):
    act = find_activity(root)
    if not act:
        print("downloads: Android project not found - nothing to remove")
        return
    cur = open(act, encoding="utf-8").read()
    new = re.sub(r"[ \t]*(//[^\n]*Downloads folder\n[ \t]*)?registerPlugin\(SaveFilePlugin\.class\);\n", "", cur)
    if new != cur:
        open(act, "w", encoding="utf-8").write(new)
    f = os.path.join(os.path.dirname(act), "SaveFilePlugin.java")
    if os.path.exists(f):
        os.remove(f)
    print("downloads: native plugin removed (files are saved through the Filesystem plugin or the share sheet)")


def main():
    root = "android/app/src/main"
    if "--remove" in sys.argv:
        remove(root)
        return
    man = os.path.join(root, "AndroidManifest.xml")
    act = find_activity(root)
    if not act or not os.path.exists(man):
        print("downloads: Android project not found - skipped")
        return
    cur = open(act, encoding="utf-8").read()
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", cur, re.M)
    if not m:
        print("downloads: could not read the app package - skipped")
        return
    pkg = m.group(1)
    fix = lambda s: s.replace("package com.sangam360.app;", "package " + pkg + ";")

    # 1) register the plugin in MainActivity
    if "SaveFilePlugin" in cur:
        pass
    elif re.search(r"extends\s+BridgeActivity\s*\{\s*\}", cur):
        open(act, "w", encoding="utf-8").write(fix(MAIN))
    elif "super.onCreate(" in cur:
        open(act, "w", encoding="utf-8").write(cur.replace("super.onCreate(", REG + "\n        super.onCreate(", 1))
    else:
        print("downloads: MainActivity has an unexpected shape - skipped")
        return
    open(os.path.join(os.path.dirname(act), "SaveFilePlugin.java"), "w", encoding="utf-8").write(fix(PLUGIN))

    # 2) manifest: only Android 9 and older need a permission to write into the shared Download folder
    x = open(man, encoding="utf-8").read()
    if 'android.permission.WRITE_EXTERNAL_STORAGE"' not in x:
        x = x.replace("</manifest>", PERM + "</manifest>", 1)
        open(man, "w", encoding="utf-8").write(x)
    print("downloads: native plugin added for package", pkg, "- files are saved in Download/Sangam360")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the build because of this part
        print("downloads: skipped -", e)
