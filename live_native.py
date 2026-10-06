"""Adds the small native Android parts of the app (run by the build after "npx cap add android").

1. Background live location: a foreground service + plugin, so that "Share live location" keeps updating when the
   app is in the background, closed from recents, or the phone is locked.
2. Contact picker: opens the phone's own contact list for "Share contact" in chat (no contacts permission is needed,
   the app only receives the one number the person picks).
If anything here does not match the Android project, it prints a note and leaves the project unchanged:
the app still builds; live location then updates only while the app is open and contacts are typed by hand.
"""
import os, re, sys

MAIN = r'''package com.sangam360.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // native part of "Share live location": keeps sending the position in the background
        registerPlugin(LiveLocationPlugin.class);
        // "Pick from my phone" in chat -> Share contact
        registerPlugin(ContactPickPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
'''

PLUGIN = r'''package com.sangam360.app;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** Called from the web app: LiveLocation.start({...}), stop(), status(), openSettings(). */
@CapacitorPlugin(name = "LiveLocation")
public class LiveLocationPlugin extends Plugin {

    private boolean granted(Context ctx, String perm) {
        return Build.VERSION.SDK_INT < 23 || ctx.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED;
    }

    @PluginMethod
    public void start(PluginCall call) {
        try {
            Context ctx = getContext();
            if (!granted(ctx, Manifest.permission.ACCESS_FINE_LOCATION) && !granted(ctx, Manifest.permission.ACCESS_COARSE_LOCATION)) {
                call.reject("Location permission is not granted");
                return;
            }
            String lid = call.getString("lid", "");
            long until = 0;
            try { until = Long.parseLong(call.getString("until", "0")); } catch (Exception ignored) { }
            if (lid == null || lid.length() == 0 || until <= System.currentTimeMillis()) {
                call.reject("Nothing to share");
                return;
            }
            Intent i = new Intent(ctx, LiveLocationService.class);
            i.setAction("start");
            for (String k : LiveLocationService.KEYS) {
                String v = call.getString(k, "");
                i.putExtra(k, v == null ? "" : v);
            }
            i.putExtra("until", until);
            if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i); else ctx.startService(i);
            // Android 13+: the "sharing live location" notification needs this permission to be visible
            if (Build.VERSION.SDK_INT >= 33 && getActivity() != null && !granted(ctx, "android.permission.POST_NOTIFICATIONS")) {
                try { getActivity().requestPermissions(new String[] { "android.permission.POST_NOTIFICATIONS" }, 7302); } catch (Exception ignored) { }
            }
            JSObject r = new JSObject();
            r.put("started", true);
            call.resolve(r);
        } catch (Exception e) {
            call.reject(e.getMessage() == null ? "Could not start live location" : e.getMessage());
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        try {
            Context ctx = getContext();
            SharedPreferences sp = ctx.getSharedPreferences(LiveLocationService.PREF, Context.MODE_PRIVATE);
            if (sp.getString("lid", "").length() > 0) {
                Intent i = new Intent(ctx, LiveLocationService.class);
                i.setAction("stop");
                if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i); else ctx.startService(i);
            }
            call.resolve();
        } catch (Exception e) {
            call.reject(e.getMessage() == null ? "Could not stop live location" : e.getMessage());
        }
    }

    /** lid = the sharing the service is looking after ("" when it has ended or was stopped from the notification). */
    @PluginMethod
    public void status(PluginCall call) {
        JSObject r = new JSObject();
        String lid = "";
        boolean free = true;
        try {
            Context ctx = getContext();
            SharedPreferences sp = ctx.getSharedPreferences(LiveLocationService.PREF, Context.MODE_PRIVATE);
            if (sp.getLong("until", 0) > System.currentTimeMillis()) lid = sp.getString("lid", "");
            // some phones pause background apps to save battery; "unrestricted" means this app is not paused
            if (Build.VERSION.SDK_INT >= 23) {
                PowerManager pm = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
                free = pm == null || pm.isIgnoringBatteryOptimizations(ctx.getPackageName());
            }
        } catch (Exception ignored) { }
        r.put("lid", lid == null ? "" : lid);
        r.put("unrestricted", free);
        r.put("v", 2);   // 2 = can also follow a school bus trip (position on the bus document, stops marked on arrival)
        call.resolve(r);
    }

    /** Opens this app's page in the phone settings (Battery -> Unrestricted is chosen there). */
    @PluginMethod
    public void openSettings(PluginCall call) {
        try {
            Context ctx = getContext();
            Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + ctx.getPackageName()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(i);
            call.resolve();
        } catch (Exception e) {
            call.reject("Could not open settings");
        }
    }
}
'''

CONTACT = r'''package com.sangam360.app;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.ContactsContract;

import androidx.activity.result.ActivityResult;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Called from the web app: ContactPick.pick() opens the phone's contact list and returns the one name + number
 * the person taps: { name, phone } or { cancelled: true }. The app never reads the address book itself, so it does
 * not need (or ask for) the contacts permission.
 */
@CapacitorPlugin(name = "ContactPick")
public class ContactPickPlugin extends Plugin {

    @PluginMethod
    public void pick(PluginCall call) {
        try {
            Intent i = new Intent(Intent.ACTION_PICK, ContactsContract.CommonDataKinds.Phone.CONTENT_URI);
            startActivityForResult(call, i, "picked");
        } catch (Exception e) {
            call.reject("No contacts app found");
        }
    }

    @ActivityCallback
    private void picked(PluginCall call, ActivityResult result) {
        if (call == null) return;
        JSObject r = new JSObject();
        Intent data = result == null ? null : result.getData();
        Uri uri = data == null ? null : data.getData();
        if (result == null || result.getResultCode() != Activity.RESULT_OK || uri == null) {
            r.put("cancelled", true);
            call.resolve(r);
            return;
        }
        Cursor c = null;
        try {
            String[] cols = { ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, ContactsContract.CommonDataKinds.Phone.NUMBER };
            c = getContext().getContentResolver().query(uri, cols, null, null, null);
            String name = "", phone = "";
            if (c != null && c.moveToFirst()) {
                String n = c.getString(0), p = c.getString(1);
                name = n == null ? "" : n;
                phone = p == null ? "" : p;
            }
            r.put("name", name);
            r.put("phone", phone);
            call.resolve(r);
        } catch (Exception e) {
            call.reject("Could not read the contact");
        } finally {
            try { if (c != null) c.close(); } catch (Exception ignored) { }
        }
    }
}
'''

SERVICE = r'''package com.sangam360.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.text.DateFormat;
import java.util.Date;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Keeps "Share live location" going when the app is in the background, closed from recents, or the phone is locked.
 * It runs as a foreground service (Android shows a notification while it is on) and writes the position straight to
 * Firestore with the signed-in user's own token, into the same place the web app writes:
 *   community chat -> societies/{sid}/presence/{uid}   field live
 *   private chat   -> societies/{sid}/dmchats/{cid}    field live.{uid}
 *   school bus trip -> societies/{sid}/buses/{bus}     field live, and arr.{key} the first time the bus is within
 *                      120 m of a student's pickup point (or the school gate) and is not just driving past.
 *                      "geo" = "k1abc,lat,lng;k9xyz,lat,lng;sch,lat,lng", "gn" = {"k1abc":"Aarav",...} for the
 *                      notification, which then reads "Next pickup: Aarav · 650 m".
 * It stops by itself when the chosen time is over, or when the person taps Stop.
 */
public class LiveLocationService extends Service implements LocationListener {
    static final String PREF = "live_location";
    static final String[] KEYS = { "project", "apiKey", "sid", "uid", "cid", "bus", "geo", "gn", "gl", "lid", "idToken", "refreshToken" };
    private static final float NEAR_M = 120f, MAX_ACC_M = 150f, SLOW_MS = 4.2f;
    private static final String CH = "live_location";
    private static final int NID = 7301;
    private static final long MIN_GAP = 12000, KEEP_ALIVE = 60000, TICK = 15000, TOKEN_LIFE = 45L * 60 * 1000;

    private LocationManager lm;
    private Handler h;
    private ExecutorService ex;
    private PowerManager.WakeLock wl;
    private volatile Location last;
    private Location sent;
    private long lastSent = 0;
    private boolean running = false, finishing = false;
    private int ended = 0;
    private String lastNote = "";
    private volatile long lastAt = 0;   // when the newest position came in; none for 20 s = the bus is standing

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            if (finishing) return;
            long now = System.currentTimeMillis();
            if (now >= prefs().getLong("until", 0)) { finish(true); return; }
            Location l = last;
            if (l != null && now - lastSent >= MIN_GAP && (l != sent || now - lastSent >= KEEP_ALIVE || reached(l).size() > 0)) push(l, 0);
            h.postDelayed(this, TICK);
        }
    };

    private SharedPreferences prefs() { return getSharedPreferences(PREF, MODE_PRIVATE); }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        h = new Handler(Looper.getMainLooper());
        ex = Executors.newSingleThreadExecutor();
    }

    @Override
    public int onStartCommand(Intent in, int flags, int startId) {
        SharedPreferences sp = prefs();
        String act = in == null ? null : in.getAction();
        if (in != null && "start".equals(act) && in.hasExtra("lid")) {
            SharedPreferences.Editor e = sp.edit();
            for (String k : KEYS) { String v = in.getStringExtra(k); e.putString(k, v == null ? "" : v); }
            e.putLong("until", in.getLongExtra("until", 0));
            e.putLong("tokenAt", System.currentTimeMillis());
            e.putString("arr", "");
            e.apply();
            last = null; sent = null; lastSent = 0; finishing = false; ended = 0; lastAt = 0;
        }
        long until = sp.getLong("until", 0);
        // a service started with startForegroundService must show its notification straight away
        if (!foreground(until)) { stopSelf(); return START_NOT_STICKY; }
        if ("stop".equals(act)) { finish(true); return START_NOT_STICKY; }
        if (sp.getString("lid", "").length() == 0 || until <= System.currentTimeMillis()) { finish(sp.getString("lid", "").length() > 0); return START_NOT_STICKY; }
        begin(until);
        return START_STICKY;
    }

    private boolean foreground(long until) {
        try {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (Build.VERSION.SDK_INT >= 26 && nm != null) {
                NotificationChannel ch = new NotificationChannel(CH, "Live location", NotificationManager.IMPORTANCE_LOW);
                ch.setDescription("Shown while you are sharing your live location");
                nm.createNotificationChannel(ch);
            }
            lastNote = "";
            Notification n = note(until, null);
            if (Build.VERSION.SDK_INT >= 29) startForeground(NID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
            else startForeground(NID, n);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /** The ongoing notification; "line" replaces the usual text (bus trip: the next pickup). */
    private Notification note(long until, String line) {
        int pf = Build.VERSION.SDK_INT >= 23 ? (PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE) : PendingIntent.FLAG_UPDATE_CURRENT;
        Intent stop = new Intent(this, LiveLocationService.class);
        stop.setAction("stop");
        PendingIntent pStop = PendingIntent.getService(this, 1, stop, pf);
        Intent open = getPackageManager().getLaunchIntentForPackage(getPackageName());
        PendingIntent pOpen = open == null ? null : PendingIntent.getActivity(this, 2, open, pf);
        String text = line != null ? line : until > 0 ? "Sharing until " + DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date(until)) + ". Tap Stop to end it now." : "Sharing your live location";
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CH) : new Notification.Builder(this);
        b.setContentTitle(line != null ? "Bus trip is on" : "Live location is on").setContentText(text).setSmallIcon(android.R.drawable.ic_menu_mylocation).setOngoing(true).setOnlyAlertOnce(true);
        if (pOpen != null) b.setContentIntent(pOpen);
        b.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", pStop);
        return b.build();
    }

    /** Bus trip: show the nearest pickup point that has not been reached yet in the notification. */
    private void nextPickup(Location l) {
        try {
            SharedPreferences sp = prefs();
            String geo = sp.getString("geo", "");
            if (l == null || geo.length() == 0 || sp.getString("bus", "").length() == 0) return;
            String done = ";" + sp.getString("arr", "") + ";", best = null;
            float bd = Float.MAX_VALUE;
            int all = 0;
            float[] d = new float[1];
            for (String g : geo.split(";")) {
                String[] p = g.split(",");
                if (p.length != 3 || "sch".equals(p[0])) continue;
                all++;
                if (done.contains(";" + p[0] + ";")) continue;
                Location.distanceBetween(l.getLatitude(), l.getLongitude(), Double.parseDouble(p[1]), Double.parseDouble(p[2]), d);
                if (d[0] < bd) { bd = d[0]; best = p[0]; }
            }
            if (all == 0) return;
            String label = sp.getString("gl", ""), line;
            if (label.length() == 0) label = "Next pickup";
            if (best == null) line = "All " + all + " points reached. End the trip in the app when you are done.";
            else {
                String name = "";
                try { name = new JSONObject(sp.getString("gn", "{}")).optString(best, ""); } catch (Exception ignored) { }
                String far = bd < 1000 ? (Math.max(10, Math.round(bd / 10f) * 10)) + " m" : (Math.round(bd / 100f) / 10f) + " km";
                line = label + ": " + (name.length() > 0 ? name : "student") + " · " + far;
            }
            if (line.equals(lastNote)) return;
            lastNote = line;
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.notify(NID, note(sp.getLong("until", 0), line));
        } catch (Exception ignored) { }
    }

    private void begin(long until) {
        if (running) return;
        running = true;
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null) {
                wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "sangam360:live");
                wl.setReferenceCounted(false);
                wl.acquire(Math.max(60000, until - System.currentTimeMillis()) + 60000);
            }
        } catch (Exception ignored) { }
        try {
            lm = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
            if (lm != null) {
                if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 10000, 5f, this, Looper.getMainLooper());
                if (lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) lm.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 10000, 5f, this, Looper.getMainLooper());
            }
        } catch (SecurityException ignored) {
        } catch (Exception ignored) { }
        h.removeCallbacks(tick);
        h.postDelayed(tick, TICK);
    }

    @Override
    public void onLocationChanged(Location l) {
        if (l == null || finishing) return;
        // prefer the more accurate fix when two providers report at nearly the same time
        Location p = last;
        if (p != null && l.getTime() - p.getTime() < 8000 && l.hasAccuracy() && p.hasAccuracy() && l.getAccuracy() > p.getAccuracy() * 2) return;
        last = l;
        lastAt = System.currentTimeMillis();
        nextPickup(l);
        // a pickup point has just been reached: say so straight away
        if (System.currentTimeMillis() - lastSent >= MIN_GAP || reached(l).size() > 0) push(l, 0);
    }

    private boolean standing() { return lastAt > 0 && System.currentTimeMillis() - lastAt >= 20000; }

    /** Bus trip only: the pickup points (keys) this position is at and that have not been reported yet. */
    private java.util.ArrayList<String> reached(Location l) {
        java.util.ArrayList<String> out = new java.util.ArrayList<String>();
        try {
            SharedPreferences sp = prefs();
            String geo = sp.getString("geo", "");
            if (l == null || geo.length() == 0 || sp.getString("bus", "").length() == 0) return out;
            if (l.hasAccuracy() && l.getAccuracy() > MAX_ACC_M) return out;
            if (l.hasSpeed() && l.getSpeed() > SLOW_MS && !standing()) return out;   // only passing by
            String done = ";" + sp.getString("arr", "") + ";";
            float[] d = new float[1];
            for (String g : geo.split(";")) {
                String[] p = g.split(",");
                if (p.length != 3 || !p[0].matches("[a-z0-9]{1,8}") || done.contains(";" + p[0] + ";")) continue;
                Location.distanceBetween(l.getLatitude(), l.getLongitude(), Double.parseDouble(p[1]), Double.parseDouble(p[2]), d);
                if (d[0] <= NEAR_M) out.add(p[0]);
            }
        } catch (Exception ignored) { }
        return out;
    }

    @Override public void onStatusChanged(String provider, int status, Bundle extras) { }
    @Override public void onProviderEnabled(String provider) { }
    @Override public void onProviderDisabled(String provider) { }

    private void push(final Location l, final long end) {
        lastSent = System.currentTimeMillis();
        sent = l;
        ex.execute(new Runnable() {
            @Override public void run() { try { send(l, end); } catch (Exception ignored) { } }
        });
    }

    /** Tell the chat that sharing has ended (if asked), then shut down. */
    private void finish(final boolean tellChat) {
        if (finishing) return;
        finishing = true;
        h.removeCallbacks(tick);
        try { if (lm != null) lm.removeUpdates(this); } catch (Exception ignored) { }
        final Location l = last;
        ex.execute(new Runnable() {
            @Override public void run() {
                try { if (tellChat) send(l, System.currentTimeMillis()); } catch (Exception ignored) { }
                prefs().edit().putString("lid", "").putString("idToken", "").putString("refreshToken", "").apply();
                h.post(new Runnable() { @Override public void run() { shutdown(); } });
            }
        });
    }

    private void shutdown() {
        running = false;
        try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception ignored) { }
        try { stopForeground(true); } catch (Exception ignored) { }
        stopSelf();
    }

    @Override
    public void onDestroy() {
        try { if (lm != null) lm.removeUpdates(this); } catch (Exception ignored) { }
        try { if (h != null) h.removeCallbacks(tick); } catch (Exception ignored) { }
        try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception ignored) { }
        try { if (ex != null) ex.shutdown(); } catch (Exception ignored) { }
        super.onDestroy();
    }

    /* ------------------------------------------------------------------ network ------------------------------------------------------------------ */

    /** The school (or the driver on another phone) ended this trip, or started a new one: stop sharing here too. */
    private void watchTrip(HttpURLConnection c, String lid) {
        try {
            java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
            java.io.InputStream in = c.getInputStream();
            byte[] buf = new byte[2048];
            int n;
            while ((n = in.read(buf)) > 0 && bo.size() < 65536) bo.write(buf, 0, n);
            in.close();
            JSONObject fl = new JSONObject(bo.toString("UTF-8")).optJSONObject("fields");
            if (fl == null) return;
            JSONObject on = fl.optJSONObject("on"), li = fl.optJSONObject("lid");
            String cur = li == null ? "" : li.optString("stringValue", "");
            boolean off = (on != null && !on.optBoolean("booleanValue", true) && cur.equals(lid)) || (cur.length() > 0 && !cur.equals(lid));
            ended = off ? ended + 1 : 0;
            if (ended >= 2) h.post(new Runnable() { @Override public void run() { finish(false); } });
        } catch (Exception ignored) { }
    }

    private static String enc(String s) throws Exception { return URLEncoder.encode(s, "UTF-8").replace("+", "%20"); }
    private static JSONObject iv(long v) throws Exception { return new JSONObject().put("integerValue", String.valueOf(v)); }
    private static JSONObject dv(double v) throws Exception { return new JSONObject().put("doubleValue", v); }
    private static JSONObject sv(String v) throws Exception { return new JSONObject().put("stringValue", v); }
    private static JSONObject map(JSONObject fields) throws Exception { return new JSONObject().put("mapValue", new JSONObject().put("fields", fields)); }

    private void send(Location l, long end) throws Exception {
        SharedPreferences sp = prefs();
        String lid = sp.getString("lid", ""), sid = sp.getString("sid", ""), uid = sp.getString("uid", ""), cid = sp.getString("cid", ""), project = sp.getString("project", "");
        if (lid.length() == 0 || sid.length() == 0 || uid.length() == 0 || project.length() == 0) return;
        String tok = token(sp);
        if (tok == null || tok.length() == 0) return;
        String bus = sp.getString("bus", "");
        boolean bb = bus.length() > 0, dm = !bb && cid.length() > 0;
        String doc = "https://firestore.googleapis.com/v1/projects/" + enc(project) + "/databases/(default)/documents/societies/" + enc(sid) + (bb ? "/buses/" + enc(bus) : dm ? "/dmchats/" + enc(cid) : "/presence/" + enc(uid));
        String base = dm ? "live.`" + uid + "`." : "live.";
        long now = System.currentTimeMillis();
        JSONObject f = new JSONObject();
        f.put("lid", sv(lid));
        f.put("until", iv(sp.getLong("until", 0)));
        f.put("end", iv(end));
        f.put("ts", iv(now));
        if (bb) f.put("spd", dv(l == null ? -1 : standing() ? 0 : l.hasSpeed() ? Math.round(l.getSpeed() * 10) / 10.0 : -1));
        if (l != null) {
            f.put("lat", dv(Math.round(l.getLatitude() * 1e6) / 1e6));
            f.put("lng", dv(Math.round(l.getLongitude() * 1e6) / 1e6));
            f.put("acc", iv(Math.round(l.hasAccuracy() ? l.getAccuracy() : 0)));
        }
        StringBuilder q = new StringBuilder();
        java.util.Iterator<String> it = f.keys();
        while (it.hasNext()) q.append(q.length() == 0 ? "?" : "&").append("updateMask.fieldPaths=").append(enc(base + it.next()));
        JSONObject fields = new JSONObject().put("live", dm ? map(new JSONObject().put(uid, map(f))) : map(f));
        java.util.ArrayList<String> hit = bb && end == 0 ? reached(l) : new java.util.ArrayList<String>();
        if (hit.size() > 0) {
            JSONObject a = new JSONObject();
            for (String k : hit) { a.put(k, iv(now)); q.append("&updateMask.fieldPaths=").append(enc("arr." + k)); }
            fields.put("arr", map(a));
        }
        // the answer then carries just these two fields: enough to notice that the trip was ended from another phone
        if (bb) q.append("&mask.fieldPaths=on&mask.fieldPaths=lid");
        byte[] body = new JSONObject().put("fields", fields).toString().getBytes("UTF-8");

        HttpURLConnection c = (HttpURLConnection) new URL(doc + q).openConnection();
        try {
            c.setConnectTimeout(15000);
            c.setReadTimeout(15000);
            try { c.setRequestMethod("PATCH"); }
            catch (Exception pe) { c.setRequestMethod("POST"); c.setRequestProperty("X-HTTP-Method-Override", "PATCH"); }
            c.setRequestProperty("Authorization", "Bearer " + tok);
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            c.setDoOutput(true);
            OutputStream os = c.getOutputStream();
            os.write(body);
            os.close();
            int code = c.getResponseCode();
            if (code == 401) sp.edit().putLong("tokenAt", 0).apply();   // token expired early: get a new one next time
            if (code == 200 && bb) {
                if (hit.size() > 0) {
                    StringBuilder d = new StringBuilder(sp.getString("arr", ""));
                    for (String k : hit) d.append(d.length() == 0 ? "" : ";").append(k);
                    sp.edit().putString("arr", d.toString()).apply();
                }
                if (end == 0) watchTrip(c, lid);
            }
        } finally {
            c.disconnect();
        }
    }

    /** The sign-in token lasts one hour; renew it with the refresh token so 8-hour sharing keeps working. */
    private String token(SharedPreferences sp) {
        String tok = sp.getString("idToken", "");
        if (tok.length() > 0 && System.currentTimeMillis() - sp.getLong("tokenAt", 0) < TOKEN_LIFE) return tok;
        String rt = sp.getString("refreshToken", ""), key = sp.getString("apiKey", "");
        if (rt.length() == 0 || key.length() == 0) return tok;
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL("https://securetoken.googleapis.com/v1/token?key=" + enc(key)).openConnection();
            c.setConnectTimeout(15000);
            c.setReadTimeout(15000);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
            c.setDoOutput(true);
            OutputStream os = c.getOutputStream();
            os.write(("grant_type=refresh_token&refresh_token=" + enc(rt)).getBytes("UTF-8"));
            os.close();
            if (c.getResponseCode() != 200) return tok;
            InputStream is = c.getInputStream();
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = is.read(buf)) > 0) bo.write(buf, 0, n);
            is.close();
            JSONObject j = new JSONObject(new String(bo.toByteArray(), "UTF-8"));
            String nt = j.optString("id_token", ""), nr = j.optString("refresh_token", "");
            if (nt.length() == 0) return tok;
            SharedPreferences.Editor e = sp.edit().putString("idToken", nt).putLong("tokenAt", System.currentTimeMillis());
            if (nr.length() > 0) e.putString("refreshToken", nr);
            e.apply();
            return nt;
        } catch (Exception e) {
            return tok;
        } finally {
            if (c != null) c.disconnect();
        }
    }
}
'''

def main():
    root = "android/app/src/main"
    man = os.path.join(root, "AndroidManifest.xml")
    act = None
    for d, _, files in os.walk(os.path.join(root, "java")):
        if "MainActivity.java" in files:
            act = os.path.join(d, "MainActivity.java")
            break
    if not act or not os.path.exists(man):
        print("live location: Android project not found - skipped")
        return
    cur = open(act, encoding="utf-8").read()
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", cur, re.M)
    if not m:
        print("live location: could not read the app package - skipped")
        return
    pkg = m.group(1)
    fix = lambda s: s.replace("package com.sangam360.app;", "package " + pkg + ";")

    # 1) register the plugins in MainActivity
    if "LiveLocationPlugin" in cur and "ContactPickPlugin" in cur:
        pass
    elif re.search(r"extends\s+BridgeActivity\s*\{\s*\}", cur):
        open(act, "w", encoding="utf-8").write(fix(MAIN))
    elif "super.onCreate(" in cur:
        add = "".join("registerPlugin(%s.class);\n        " % n for n in ("LiveLocationPlugin", "ContactPickPlugin") if n not in cur)
        open(act, "w", encoding="utf-8").write(cur.replace("super.onCreate(", add + "super.onCreate(", 1))
    else:
        print("live location: MainActivity has an unexpected shape - skipped")
        return
    d = os.path.dirname(act)
    open(os.path.join(d, "LiveLocationPlugin.java"), "w", encoding="utf-8").write(fix(PLUGIN))
    open(os.path.join(d, "LiveLocationService.java"), "w", encoding="utf-8").write(fix(SERVICE))
    open(os.path.join(d, "ContactPickPlugin.java"), "w", encoding="utf-8").write(fix(CONTACT))

    # 2) manifest: the service and the permissions a location foreground service needs
    x = open(man, encoding="utf-8").read()
    if "LiveLocationService" not in x:
        svc = '        <service android:name="' + pkg + '.LiveLocationService" android:exported="false" android:foregroundServiceType="location" android:stopWithTask="false" />\n    </application>'
        x = x.replace("</application>", svc, 1)
    perms = ["FOREGROUND_SERVICE", "FOREGROUND_SERVICE_LOCATION", "WAKE_LOCK", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "POST_NOTIFICATIONS", "INTERNET"]
    add = "".join('    <uses-permission android:name="android.permission.%s" />\n' % p for p in perms if ("android.permission." + p + '"') not in x)
    x = x.replace("</manifest>", add + "</manifest>", 1)
    open(man, "w", encoding="utf-8").write(x)
    print("live location: native service added for package", pkg)
    print("contact picker: native plugin added")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the build because of this optional part
        print("live location: skipped -", e)
