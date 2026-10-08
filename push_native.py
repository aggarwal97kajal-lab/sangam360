"""Push notifications for the Android app (run by the build after "npx cap add android" and brand.py).

What it adds:
  - S360MessagingService  receives the messages the Sangam360 server sends through Firebase Cloud Messaging (free),
                          also when the app is closed, and shows them as notifications:
                            * with the app's name (Android puts it at the top) and the Sangam360 logo
                            * a chat is one notification per conversation that grows with each new message, like
                              WhatsApp, with a "Reply" box: the answer is sent without opening the app
                            * notices, visitors, bills, complaints, leave ... each as its own notification
                          While the app is open on screen nothing is shown here (the app shows its own alert).
  - S360ReplyReceiver     sends a reply typed in a notification to the server
  - S360Push (plugin)     used by the web app: asks for the notification permission, gives the phone's push token,
                          keeps the key for replying, tells the app which screen to open when a notification is tapped
  - the small white status-bar icon, made from the logo (ic_stat_s360)

"python3 push_native.py --remove" takes all of it out again (a fallback of the build: the app then builds as before,
without notifications when it is closed). "--emit DIR" only writes the Java files into DIR (for checking them).
If anything here does not match the Android project it prints a note and leaves the project unchanged.
"""
import os, re, sys

PKG0 = "com.sangam360.app"
NAMES = ("S360PushPlugin", "S360MessagingService", "S360ReplyReceiver", "S360Notifier")

MAIN = r'''package com.sangam360.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // push notifications: permission, token, reply key, opening from a notification
        registerPlugin(S360PushPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
'''

PLUGIN = r'''package com.sangam360.app;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import com.google.android.gms.tasks.OnCompleteListener;
import com.google.android.gms.tasks.Task;
import com.google.firebase.messaging.FirebaseMessaging;

/**
 * Called from the web app:
 *   S360Push.register()                          -> { token, granted }   asks for the permission (Android 13+) first
 *   S360Push.setAuth({ server, device, key, sid, uid, name })   what a Reply in a notification needs
 *   S360Push.clearAuth()                         on log-out: no more replies from this phone
 *   S360Push.takeOpen()                          -> { open, sid }       the screen of the notification that was tapped
 *   S360Push.clear({ tag })                      the conversation is open in the app: its notification goes
 *   S360Push.status()                            -> { granted, enabled, token, auth }   for "Check notifications"
 *   event "open" { open, sid }                   a notification was tapped while the app was running
 */
@CapacitorPlugin(
    name = "S360Push",
    permissions = { @Permission(alias = "notifications", strings = { "android.permission.POST_NOTIFICATIONS" }) }
)
public class S360PushPlugin extends Plugin {

    static volatile boolean foreground = false;

    @Override
    public void load() {
        foreground = true;
        try { keepOpen(getActivity().getIntent()); } catch (Exception ignored) { }
    }

    @Override
    protected void handleOnResume() { foreground = true; }

    @Override
    protected void handleOnPause() { foreground = false; }

    @Override
    protected void handleOnDestroy() { foreground = false; }

    @Override
    protected void handleOnNewIntent(Intent intent) {
        if (keepOpen(intent)) {
            JSObject o = new JSObject();
            SharedPreferences sp = S360Notifier.prefs(getContext());
            o.put("open", sp.getString("open", ""));
            o.put("sid", sp.getString("openSid", ""));
            notifyListeners("open", o, true);
        }
    }

    /** a notification was tapped: remember where it should take the person */
    private boolean keepOpen(Intent i) {
        if (i == null || !i.hasExtra(S360Notifier.EXTRA_OPEN)) return false;
        String open = i.getStringExtra(S360Notifier.EXTRA_OPEN), sid = i.getStringExtra(S360Notifier.EXTRA_SID);
        i.removeExtra(S360Notifier.EXTRA_OPEN);
        S360Notifier.prefs(getContext()).edit().putString("open", open == null ? "" : open).putString("openSid", sid == null ? "" : sid).apply();
        return true;
    }

    @PluginMethod
    public void register(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 33 && getPermissionState("notifications") != PermissionState.GRANTED) {
            requestPermissionForAlias("notifications", call, "permAnswer");
            return;
        }
        token(call, true);
    }

    @PermissionCallback
    private void permAnswer(PluginCall call) {
        token(call, getPermissionState("notifications") == PermissionState.GRANTED);
    }

    private void token(final PluginCall call, final boolean granted) {
        try {
            FirebaseMessaging.getInstance().getToken().addOnCompleteListener(new OnCompleteListener<String>() {
                @Override
                public void onComplete(Task<String> task) {
                    if (!task.isSuccessful() || task.getResult() == null) { call.reject("No push token on this phone right now"); return; }
                    S360Notifier.prefs(getContext()).edit().putString("token", task.getResult()).apply();
                    JSObject r = new JSObject();
                    r.put("token", task.getResult());
                    r.put("granted", granted);
                    call.resolve(r);
                }
            });
        } catch (Exception e) {
            call.reject("Push notifications are not available in this build");
        }
    }

    @PluginMethod
    public void setAuth(PluginCall call) {
        S360Notifier.prefs(getContext()).edit()
            .putString("server", call.getString("server", ""))
            .putString("device", call.getString("device", ""))
            .putString("key", call.getString("key", ""))
            .putString("sid", call.getString("sid", ""))
            .putString("uid", call.getString("uid", ""))
            .putString("name", call.getString("name", ""))
            .apply();
        call.resolve();
    }

    @PluginMethod
    public void clearAuth(PluginCall call) {
        Context ctx = getContext();
        S360Notifier.prefs(ctx).edit().remove("device").remove("key").remove("uid").remove("name").apply();
        S360Notifier.cancelAll(ctx);
        call.resolve();
    }

    @PluginMethod
    public void takeOpen(PluginCall call) {
        SharedPreferences sp = S360Notifier.prefs(getContext());
        JSObject r = new JSObject();
        r.put("open", sp.getString("open", ""));
        r.put("sid", sp.getString("openSid", ""));
        sp.edit().remove("open").remove("openSid").apply();
        call.resolve(r);
    }

    @PluginMethod
    public void status(PluginCall call) {
        Context ctx = getContext();
        SharedPreferences sp = S360Notifier.prefs(ctx);
        JSObject r = new JSObject();
        r.put("granted", Build.VERSION.SDK_INT < 33 || getPermissionState("notifications") == PermissionState.GRANTED);
        boolean on = true;
        try { on = androidx.core.app.NotificationManagerCompat.from(ctx).areNotificationsEnabled(); } catch (Exception ignored) { }
        r.put("enabled", on);
        r.put("token", sp.getString("token", "").length() > 0);
        r.put("auth", sp.getString("key", "").length() > 0);
        call.resolve(r);
    }

    @PluginMethod
    public void clear(PluginCall call) {
        S360Notifier.cancel(getContext(), call.getString("tag", ""));
        call.resolve();
    }
}
'''

SERVICE = r'''package com.sangam360.app;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;

/** Every push from the Sangam360 server arrives here, also when the app is closed. */
public class S360MessagingService extends FirebaseMessagingService {

    @Override
    public void onNewToken(String token) {
        // the app sends the new token to the server the next time it is opened
        S360Notifier.prefs(this).edit().putString("token", token).apply();
    }

    @Override
    public void onMessageReceived(RemoteMessage message) {
        Map<String, String> d = message.getData();
        if (d == null || d.isEmpty()) return;
        // the app is open on screen: it shows its own alert, so nothing is shown twice (a test from "Check notifications" is shown anyway)
        if (S360PushPlugin.foreground && !"1".equals(d.get("force"))) return;
        S360Notifier.show(this, d);
    }
}
'''

RECEIVER = r'''package com.sangam360.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;

import androidx.core.app.RemoteInput;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** "Reply" typed in a chat notification: sent to the server, which writes it as this person's message. */
public class S360ReplyReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(final Context ctx, Intent intent) {
        Bundle res = RemoteInput.getResultsFromIntent(intent);
        final CharSequence typed = res == null ? null : res.getCharSequence(S360Notifier.REPLY_KEY);
        final String tag = intent.getStringExtra(S360Notifier.EXTRA_TAG), sid = intent.getStringExtra(S360Notifier.EXTRA_SID);
        if (typed == null || tag == null) return;
        final String text = typed.toString().trim();
        if (text.length() == 0) { S360Notifier.refresh(ctx, tag); return; }
        final PendingResult pending = goAsync();
        new Thread(new Runnable() {
            @Override
            public void run() {
                String err = null;
                try { err = send(ctx, sid, tag, text); }
                catch (Exception e) { err = "Not sent. Check your internet and reply again."; }
                finally {
                    try {
                        if (err == null) S360Notifier.addOwn(ctx, tag, text);
                        else S360Notifier.failed(ctx, tag, text, err);
                    } catch (Exception ignored) { }
                    pending.finish();
                }
            }
        }).start();
    }

    /** null when the server took the message, otherwise what to tell the person */
    private static String send(Context ctx, String sid, String tag, String text) throws Exception {
        SharedPreferences sp = S360Notifier.prefs(ctx);
        String server = sp.getString("server", ""), device = sp.getString("device", ""), key = sp.getString("key", "");
        if (server.length() == 0 || device.length() == 0 || key.length() == 0) return "Open the app once to reply from here.";
        JSONObject body = new JSONObject();
        body.put("device", device);
        body.put("key", key);
        body.put("sid", sid == null || sid.length() == 0 ? sp.getString("sid", "") : sid);
        body.put("to", tag);
        body.put("text", text);
        HttpURLConnection c = (HttpURLConnection) new URL(server.replaceAll("/+$", "") + "/v1/push/reply").openConnection();
        try {
            c.setConnectTimeout(20000);
            c.setReadTimeout(25000);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            c.setDoOutput(true);
            OutputStream os = c.getOutputStream();
            os.write(body.toString().getBytes("UTF-8"));
            os.close();
            int code = c.getResponseCode();
            if (code >= 200 && code < 300) return null;
            InputStream is = c.getErrorStream();
            String msg = "";
            if (is != null) {
                ByteArrayOutputStream bo = new ByteArrayOutputStream();
                byte[] buf = new byte[4096];
                int n;
                while ((n = is.read(buf)) > 0) bo.write(buf, 0, n);
                is.close();
                try { msg = new JSONObject(new String(bo.toByteArray(), "UTF-8")).getJSONObject("error").optString("message", ""); } catch (Exception ignored) { }
            }
            return msg.length() > 0 ? msg : "Not sent. Open the app and try again.";
        } finally {
            c.disconnect();
        }
    }
}
'''

NOTIFIER = r'''package com.sangam360.app;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.app.Person;
import androidx.core.app.RemoteInput;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Map;

/**
 * How a push looks on the phone. The server sends (all strings):
 *   k kind (chat, ann, sos, bill, comp, gate, leave, join, gen, bus) · t title · b text · org organisation name
 *   tag one notification per tag (a chat: "d:<chat>" or "g:<org>:<room>") · open the screen to open · sid
 *   reply "1" = a chat that can be answered from the notification · frm sender · grp name of a group chat
 */
final class S360Notifier {
    static final String PREF = "s360push";
    static final String EXTRA_OPEN = "s360open", EXTRA_SID = "s360sid", EXTRA_TAG = "s360tag";
    static final String REPLY_KEY = "s360reply";
    private static final String CH_CHAT = "s360_chat", CH_ALERT = "s360_alerts", CH_INFO = "s360_updates", CH_BUS = "s360_bus";
    private static final int ACCENT = Color.parseColor("#5B3DF5");
    private static final int KEEP = 8;   // messages kept in a chat notification

    private S360Notifier() { }

    static SharedPreferences prefs(Context ctx) { return ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE); }

    private static int idOf(String tag) { return 0x5300000 + ((tag == null ? "" : tag).hashCode() & 0xFFFFF); }

    private static String s(Map<String, String> d, String k) { String v = d.get(k); return v == null ? "" : v; }

    private static void channels(Context ctx) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        NotificationChannel chat = new NotificationChannel(CH_CHAT, "Chats", NotificationManager.IMPORTANCE_HIGH);
        chat.setDescription("Community chat and private messages");
        NotificationChannel alert = new NotificationChannel(CH_ALERT, "SOS & emergency alerts", NotificationManager.IMPORTANCE_HIGH);
        alert.setDescription("SOS and emergency notices");
        alert.enableVibration(true);
        NotificationChannel info = new NotificationChannel(CH_INFO, "Updates", NotificationManager.IMPORTANCE_DEFAULT);
        info.setDescription("Notices, visitors, parcels, bills, complaints, leave and other updates");
        nm.createNotificationChannel(chat);
        nm.createNotificationChannel(alert);
        nm.createNotificationChannel(info);
        NotificationChannel bus = new NotificationChannel(CH_BUS, "School bus", NotificationManager.IMPORTANCE_HIGH);
        bus.setDescription("The bus has started, is near, has arrived; reached school");
        bus.enableVibration(true);
        nm.createNotificationChannel(bus);
    }

    private static int smallIcon(Context ctx) {
        int id = ctx.getResources().getIdentifier("ic_stat_s360", "drawable", ctx.getPackageName());
        if (id == 0) id = ctx.getApplicationInfo().icon;
        return id != 0 ? id : android.R.drawable.ic_dialog_info;
    }

    private static Bitmap logo(Context ctx) {
        try {
            int id = ctx.getResources().getIdentifier("ic_launcher", "mipmap", ctx.getPackageName());
            return id == 0 ? null : BitmapFactory.decodeResource(ctx.getResources(), id);
        } catch (Exception e) { return null; }
    }

    /** tapping the notification opens the app on the right screen */
    private static PendingIntent tap(Context ctx, String open, String sid, int id) {
        Intent i = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        if (i == null) i = new Intent();
        i.setPackage(ctx.getPackageName());
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        i.putExtra(EXTRA_OPEN, open);
        i.putExtra(EXTRA_SID, sid);
        int fl = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0);
        return PendingIntent.getActivity(ctx, id, i, fl);
    }

    private static boolean allowed(Context ctx) {
        if (Build.VERSION.SDK_INT >= 33 && ctx.checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) return false;
        return NotificationManagerCompat.from(ctx).areNotificationsEnabled();
    }

    private static void post(Context ctx, int id, NotificationCompat.Builder b) {
        try { NotificationManagerCompat.from(ctx).notify(id, b.build()); } catch (SecurityException ignored) { }
    }

    static void show(Context ctx, Map<String, String> d) {
        if (!allowed(ctx)) return;
        channels(ctx);
        String kind = s(d, "k"), tag = s(d, "tag"), sid = s(d, "sid");
        if (tag.length() == 0) tag = kind + ":" + s(d, "ts");
        if ("1".equals(s(d, "reply"))) {
            JSONArray h = history(ctx, tag);
            try {
                JSONObject m = new JSONObject();
                m.put("f", s(d, "frm").length() > 0 ? s(d, "frm") : s(d, "t"));
                m.put("b", s(d, "b"));
                m.put("ts", System.currentTimeMillis());
                h.put(m);
            } catch (Exception ignored) { }
            JSONObject meta = new JSONObject();
            try {
                meta.put("open", s(d, "open")); meta.put("sid", sid); meta.put("org", s(d, "org")); meta.put("grp", s(d, "grp"));
                meta.put("men", s(d, "men"));
            } catch (Exception ignored) { }
            save(ctx, tag, trim(h), meta);
            chat(ctx, tag, false, null);
            return;
        }
        boolean busK = "bus".equals(kind);
        String ch = "sos".equals(kind) ? CH_ALERT : busK ? CH_BUS : CH_INFO;
        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, ch)
            .setSmallIcon(smallIcon(ctx))
            .setColor(ACCENT)
            .setLargeIcon(logo(ctx))
            .setContentTitle(s(d, "t"))
            .setContentText(s(d, "b"))
            .setStyle(new NotificationCompat.BigTextStyle().bigText(s(d, "b")))
            .setSubText(s(d, "org"))
            .setAutoCancel(true)
            .setPriority("sos".equals(kind) ? NotificationCompat.PRIORITY_MAX : busK ? NotificationCompat.PRIORITY_HIGH : NotificationCompat.PRIORITY_DEFAULT)
            .setCategory("sos".equals(kind) ? NotificationCompat.CATEGORY_ALARM : NotificationCompat.CATEGORY_EVENT)
            .setContentIntent(tap(ctx, s(d, "open"), sid, idOf(tag)));
        post(ctx, idOf(tag), b);
    }

    /* ---------------- a chat: one notification per conversation, like WhatsApp ---------------- */

    private static JSONArray history(Context ctx, String tag) {
        try { return new JSONArray(prefs(ctx).getString("h:" + tag, "[]")); } catch (Exception e) { return new JSONArray(); }
    }

    private static JSONObject meta(Context ctx, String tag) {
        try { return new JSONObject(prefs(ctx).getString("m:" + tag, "{}")); } catch (Exception e) { return new JSONObject(); }
    }

    private static JSONArray trim(JSONArray h) {
        if (h.length() <= KEEP) return h;
        JSONArray out = new JSONArray();
        for (int i = h.length() - KEEP; i < h.length(); i++) out.put(h.opt(i));
        return out;
    }

    private static void save(Context ctx, String tag, JSONArray h, JSONObject meta) {
        SharedPreferences.Editor e = prefs(ctx).edit().putString("h:" + tag, h.toString());
        if (meta != null) e.putString("m:" + tag, meta.toString());
        e.apply();
    }

    /** builds (or rebuilds) the conversation's notification from what is kept for it */
    private static void chat(Context ctx, String tag, boolean quiet, String note) {
        JSONArray h = history(ctx, tag);
        JSONObject meta = meta(ctx, tag);
        if (h.length() == 0) return;
        String myName = prefs(ctx).getString("name", "");
        Person me = new Person.Builder().setName("You").setKey("me").build();
        NotificationCompat.MessagingStyle st = new NotificationCompat.MessagingStyle(me);
        String grp = meta.optString("grp", "");
        boolean group = tag.startsWith("g:");
        if (group) {
            st.setConversationTitle(grp.length() > 0 ? grp : meta.optString("org", ""));
            st.setGroupConversation(true);
        }
        String last = "", lastFrom = "";
        int theirs = 0;
        for (int i = 0; i < h.length(); i++) {
            JSONObject m = h.optJSONObject(i);
            if (m == null) continue;
            boolean mine = m.optBoolean("me", false);
            Person p = mine ? null : new Person.Builder().setName(m.optString("f", "Message")).setKey("p:" + m.optString("f", "")).build();
            st.addMessage(m.optString("b", ""), m.optLong("ts", System.currentTimeMillis()), p);
            if (!mine) { theirs++; last = m.optString("b", ""); lastFrom = m.optString("f", ""); }
        }
        if (note != null) st.addMessage(note, System.currentTimeMillis(), (Person) null);
        int id = idOf(tag);
        String sid = meta.optString("sid", "");
        RemoteInput ri = new RemoteInput.Builder(REPLY_KEY).setLabel("Reply" + (myName.length() > 0 ? " as " + myName : "")).build();
        Intent ri2 = new Intent(ctx, S360ReplyReceiver.class);
        ri2.setPackage(ctx.getPackageName());
        ri2.putExtra(EXTRA_TAG, tag);
        ri2.putExtra(EXTRA_SID, sid);
        int fl = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
        PendingIntent rp = PendingIntent.getBroadcast(ctx, id, ri2, fl);
        int replyIcon = ctx.getResources().getIdentifier("ic_stat_s360", "drawable", ctx.getPackageName());
        NotificationCompat.Action reply = new NotificationCompat.Action.Builder(replyIcon != 0 ? replyIcon : android.R.drawable.ic_menu_send, "Reply", rp)
            .addRemoteInput(ri)
            .setAllowGeneratedReplies(true)
            .setSemanticAction(NotificationCompat.Action.SEMANTIC_ACTION_REPLY)
            .setShowsUserInterface(false)
            .build();
        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, CH_CHAT)
            .setSmallIcon(smallIcon(ctx))
            .setColor(ACCENT)
            .setLargeIcon(logo(ctx))
            .setStyle(st)
            .setContentTitle(group ? (grp.length() > 0 ? grp : meta.optString("org", "")) : lastFrom)
            .setContentText(group && lastFrom.length() > 0 ? lastFrom + ": " + last : last)
            .setSubText(meta.optString("org", ""))
            .setNumber(theirs)
            .setAutoCancel(true)
            .setOnlyAlertOnce(quiet)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setContentIntent(tap(ctx, meta.optString("open", ""), sid, id))
            .addAction(reply);
        if (quiet) b.setSilent(true);
        post(ctx, id, b);
    }

    /** the reply went through: it is shown in the conversation as "You", without a new sound */
    static void addOwn(Context ctx, String tag, String text) {
        JSONArray h = history(ctx, tag);
        try { JSONObject m = new JSONObject(); m.put("f", "You"); m.put("b", text); m.put("ts", System.currentTimeMillis()); m.put("me", true); h.put(m); } catch (Exception ignored) { }
        save(ctx, tag, trim(h), null);
        chat(ctx, tag, true, null);
    }

    /** the reply did not go through: the conversation says so, and the text is not lost (it is shown) */
    static void failed(Context ctx, String tag, String text, String why) {
        chat(ctx, tag, true, "⚠️ Not sent: \"" + text + "\" · " + why);
    }

    /** an empty reply: the spinner of the Reply box stops */
    static void refresh(Context ctx, String tag) { chat(ctx, tag, true, null); }

    static void cancel(Context ctx, String tag) {
        if (tag == null || tag.length() == 0) return;
        try { NotificationManagerCompat.from(ctx).cancel(idOf(tag)); } catch (Exception ignored) { }
        prefs(ctx).edit().remove("h:" + tag).remove("m:" + tag).apply();
    }

    static void cancelAll(Context ctx) {
        try { NotificationManagerCompat.from(ctx).cancelAll(); } catch (Exception ignored) { }
        SharedPreferences sp = prefs(ctx);
        SharedPreferences.Editor e = sp.edit();
        for (String k : sp.getAll().keySet()) if (k.startsWith("h:") || k.startsWith("m:")) e.remove(k);
        e.apply();
    }
}
'''

SOURCES = {"S360PushPlugin": PLUGIN, "S360MessagingService": SERVICE, "S360ReplyReceiver": RECEIVER, "S360Notifier": NOTIFIER}

GRADLE_DEPS = '''
// sangam-push-start
dependencies {
    implementation "com.google.firebase:firebase-messaging:24.0.0"
}
// sangam-push-end
'''
COLOR = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="s360_notify">#5B3DF5</color>\n</resources>\n'


def manifest_parts(pkg):
    return ('        <!-- sangam-push-start -->\n'
            '        <service android:name="' + pkg + '.S360MessagingService" android:exported="false">\n'
            '            <intent-filter><action android:name="com.google.firebase.MESSAGING_EVENT" /></intent-filter>\n'
            '        </service>\n'
            '        <receiver android:name="' + pkg + '.S360ReplyReceiver" android:exported="false" />\n'
            '        <meta-data android:name="com.google.firebase.messaging.default_notification_icon" android:resource="@drawable/ic_stat_s360" />\n'
            '        <meta-data android:name="com.google.firebase.messaging.default_notification_color" android:resource="@color/s360_notify" />\n'
            '        <meta-data android:name="com.google.firebase.messaging.default_notification_channel_id" android:value="s360_updates" />\n'
            '        <!-- sangam-push-end -->\n')


def find_activity(root):
    for d, _, files in os.walk(os.path.join(root, "java")):
        if "MainActivity.java" in files:
            return os.path.join(d, "MainActivity.java")
    return None


def strip_block(text, start, end):
    return re.sub(r"\n?[ \t]*" + re.escape(start) + r".*?" + re.escape(end) + r"[ \t]*\n?", "\n", text, flags=re.S)


def status_icons(res):
    """The small icon of the status bar must be white on transparent: made from the logo the brand step drew."""
    try:
        from PIL import Image
    except Exception:
        print("push: Pillow not installed - the app icon is used in the status bar")
        return False
    src = None
    for d in ("xxxhdpi", "xxhdpi", "xhdpi"):
        p = os.path.join(res, "mipmap-" + d, "ic_launcher_foreground.png")
        if os.path.exists(p):
            src = p
            break
    if not src:
        print("push: logo not found - the app icon is used in the status bar")
        return False
    im = Image.open(src).convert("RGBA")
    px = im.load()
    w, h = im.size
    out = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    po = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 40:
                continue
            # the logo's coloured strokes become white; the white disc behind it stays empty
            ink = 255 - min(r, g, b)
            sat = max(r, g, b) - min(r, g, b)
            v = max(ink, sat)
            if v > 70:
                po[x, y] = (255, 255, 255, a if v > 110 else a * (v - 70) // 40)
    box = out.getbbox()
    if not box:
        print("push: logo is empty - the app icon is used in the status bar")
        return False
    out = out.crop(box)
    side = max(out.size)
    sq = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    sq.alpha_composite(out, ((side - out.size[0]) // 2, (side - out.size[1]) // 2))
    for d, s in {"mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96}.items():
        folder = os.path.join(res, "drawable-" + d)
        os.makedirs(folder, exist_ok=True)
        inner = int(s * 0.84)
        icon = Image.new("RGBA", (s, s), (255, 255, 255, 0))
        icon.alpha_composite(sq.resize((inner, inner), Image.LANCZOS), ((s - inner) // 2, (s - inner) // 2))
        icon.save(os.path.join(folder, "ic_stat_s360.png"))
    return True


def remove(root):
    act = find_activity(root)
    if act:
        cur = open(act, encoding="utf-8").read()
        new = re.sub(r"[ \t]*(//[^\n]*push notifications[^\n]*\n[ \t]*)?registerPlugin\(S360PushPlugin\.class\);\n", "", cur)
        if new != cur:
            open(act, "w", encoding="utf-8").write(new)
        for n in NAMES:
            f = os.path.join(os.path.dirname(act), n + ".java")
            if os.path.exists(f):
                os.remove(f)
    man = os.path.join(root, "AndroidManifest.xml")
    if os.path.exists(man):
        x = open(man, encoding="utf-8").read()
        open(man, "w", encoding="utf-8").write(strip_block(x, "<!-- sangam-push-start -->", "<!-- sangam-push-end -->"))
    g = "android/app/build.gradle"
    if os.path.exists(g):
        x = open(g, encoding="utf-8").read()
        open(g, "w", encoding="utf-8").write(strip_block(x, "// sangam-push-start", "// sangam-push-end"))
    print("push: taken out of this build (no notifications while the app is closed)")


def main():
    if "--emit" in sys.argv:
        out = sys.argv[sys.argv.index("--emit") + 1]
        os.makedirs(out, exist_ok=True)
        for n, src in SOURCES.items():
            open(os.path.join(out, n + ".java"), "w", encoding="utf-8").write(src)
        open(os.path.join(out, "MainActivity.java"), "w", encoding="utf-8").write(MAIN)
        print("push: sources written to", out)
        return
    root = "android/app/src/main"
    if "--remove" in sys.argv:
        remove(root)
        return
    man = os.path.join(root, "AndroidManifest.xml")
    act = find_activity(root)
    gradle = "android/app/build.gradle"
    if not act or not os.path.exists(man) or not os.path.exists(gradle):
        print("push: Android project not found - skipped")
        return
    if not os.path.exists("android/app/google-services.json"):
        print("push: google-services.json is not in the project - skipped (Firebase is needed for push)")
        return
    cur = open(act, encoding="utf-8").read()
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", cur, re.M)
    if not m:
        print("push: could not read the app package - skipped")
        return
    pkg = m.group(1)
    fix = lambda s: s.replace("package " + PKG0 + ";", "package " + pkg + ";")

    # 1) the plugin in MainActivity
    if "S360PushPlugin" in cur:
        pass
    elif re.search(r"extends\s+BridgeActivity\s*\{\s*\}", cur):
        open(act, "w", encoding="utf-8").write(fix(MAIN))
    elif "super.onCreate(" in cur:
        open(act, "w", encoding="utf-8").write(cur.replace("super.onCreate(", "registerPlugin(S360PushPlugin.class);\n        super.onCreate(", 1))
    else:
        print("push: MainActivity has an unexpected shape - skipped")
        return
    for n, src in SOURCES.items():
        open(os.path.join(os.path.dirname(act), n + ".java"), "w", encoding="utf-8").write(fix(src))

    # 2) resources: the status-bar icon and the accent colour
    res = os.path.join(root, "res")
    if not status_icons(res):
        # an icon must exist for the manifest entry: the launcher icon is copied in its place
        for d in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
            s = os.path.join(res, "mipmap-" + d, "ic_launcher.png")
            if os.path.exists(s):
                os.makedirs(os.path.join(res, "drawable-" + d), exist_ok=True)
                open(os.path.join(res, "drawable-" + d, "ic_stat_s360.png"), "wb").write(open(s, "rb").read())
    os.makedirs(os.path.join(res, "values"), exist_ok=True)
    open(os.path.join(res, "values", "s360_push.xml"), "w", encoding="utf-8").write(COLOR)

    # 3) manifest: the service that receives pushes, the reply receiver, defaults
    x = strip_block(open(man, encoding="utf-8").read(), "<!-- sangam-push-start -->", "<!-- sangam-push-end -->")
    x = x.replace("</application>", manifest_parts(pkg) + "    </application>", 1)
    if "android.permission.POST_NOTIFICATIONS" not in x:
        x = x.replace("</manifest>", '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n</manifest>', 1)
    open(man, "w", encoding="utf-8").write(x)

    # 4) Firebase Cloud Messaging library
    g = strip_block(open(gradle, encoding="utf-8").read(), "// sangam-push-start", "// sangam-push-end")
    open(gradle, "w", encoding="utf-8").write(g + GRADLE_DEPS)
    print("push: notifications with reply added for package", pkg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the build because of this part
        print("push: skipped -", e)
