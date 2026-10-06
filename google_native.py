"""Run by the build after live_native.py and before "npx cap sync".

1. Signing: if the build has the app's own signing key (android/app/sangam360.keystore, written by the workflow from
   the KEYSTORE_BASE64 secret) the APK is signed with it, so every build has the same signature: a new APK installs
   over the old one, and Google sign-in can trust the app.
2. Google sign-in: adds a small plugin (GoogleLogin.signIn) and its libraries, and tells the web app the project's
   Google "web client ID", read from google-services.json.
   The plugin looks its libraries up by name while the app runs, so it cannot stop the app from building.

"python3 google_native.py --remove" takes the Google part out again, "--plain" takes the signing out as well
(both are used by the build as fallbacks, so a problem here cannot leave you without an APK).
If anything here does not match the project it prints a note and leaves that part out: the app still builds.
"""
import json, os, re, subprocess, sys

APP = "android/app"
GRADLE = os.path.join(APP, "build.gradle")
DEPS = '''
// sangam-google-start
dependencies {
    implementation "androidx.credentials:credentials:1.3.0"
    implementation "androidx.credentials:credentials-play-services-auth:1.3.0"
    implementation "com.google.android.libraries.identity.googleid:googleid:1.1.1"
}
// sangam-google-end
'''
SIGN = '''
// sangam-signing-start
def sangamKey = file("sangam360.keystore")
def sangamPass = (System.getenv("KEYSTORE_PASSWORD") ?: "").trim()
if (sangamKey.exists() && sangamPass) {
    android {
        signingConfigs {
            debug {
                storeFile sangamKey
                storePassword sangamPass
                keyAlias "sangam360"
                keyPassword sangamPass
                storeType "pkcs12"
            }
        }
    }
}
// sangam-signing-end
'''

PLUGIN = r'''package com.sangam360.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;

import androidx.activity.result.ActivityResult;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.Executor;

/**
 * Called from the web app: GoogleLogin.signIn({ clientId }) shows the phone's Google account chooser and returns
 * { idToken } (the web app signs in to Firebase with it) or { cancelled: true }.
 * The Google libraries are looked up by name at run time: first the current one (Credential Manager), and if that
 * is not possible on the phone the older Google Sign-In screen.
 */
@CapacitorPlugin(name = "GoogleLogin")
public class GoogleLoginPlugin extends Plugin {
    private static final String KEY_ID_TOKEN = "com.google.android.libraries.identity.googleid.BUNDLE_KEY_ID_TOKEN";
    private String pendingClient = "";

    @PluginMethod
    public void signIn(final PluginCall call) {
        final String clientId = call.getString("clientId", "");
        final Activity act = getActivity();
        if (clientId == null || clientId.length() == 0) { call.reject("Google sign-in is not set up", "not_configured"); return; }
        if (act == null) { call.reject("No screen to show Google on", "unavailable"); return; }
        pendingClient = clientId;
        act.runOnUiThread(new Runnable() {
            @Override public void run() {
                try { modern(call, act, clientId); }
                catch (Throwable t) { classic(call, act, clientId); }
            }
        });
    }

    private void done(PluginCall call, String token) {
        if (token == null || token.length() == 0) { call.reject("Google did not return a sign-in token", "no_token"); return; }
        JSObject r = new JSObject();
        r.put("idToken", token);
        call.resolve(r);
    }

    private void cancelled(PluginCall call) {
        JSObject r = new JSObject();
        r.put("cancelled", true);
        call.resolve(r);
    }

    /* ---------- Credential Manager ---------- */
    private void modern(final PluginCall call, final Activity act, final String clientId) throws Exception {
        Class<?> cmC = Class.forName("androidx.credentials.CredentialManager");
        Object cm = cmC.getMethod("create", Context.class).invoke(null, act);
        Object opt;
        try {
            Class<?> b = Class.forName("com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption$Builder");
            Object ob = b.getConstructor(String.class).newInstance(clientId);
            opt = b.getMethod("build").invoke(ob);
        } catch (Throwable t) {
            Class<?> b = Class.forName("com.google.android.libraries.identity.googleid.GetGoogleIdOption$Builder");
            Object ob = b.getConstructor().newInstance();
            b.getMethod("setFilterByAuthorizedAccounts", boolean.class).invoke(ob, false);
            b.getMethod("setServerClientId", String.class).invoke(ob, clientId);
            opt = b.getMethod("build").invoke(ob);
        }
        Class<?> rbC = Class.forName("androidx.credentials.GetCredentialRequest$Builder");
        Object rb = rbC.getConstructor().newInstance();
        rbC.getMethod("addCredentialOption", Class.forName("androidx.credentials.CredentialOption")).invoke(rb, opt);
        Object req = rbC.getMethod("build").invoke(rb);
        final Class<?> cbI = Class.forName("androidx.credentials.CredentialManagerCallback");
        final boolean[] over = { false };
        Object cb = Proxy.newProxyInstance(cbI.getClassLoader(), new Class<?>[] { cbI }, new InvocationHandler() {
            @Override public Object invoke(Object proxy, Method m, Object[] args) {
                String n = m.getName();
                if ("hashCode".equals(n)) return System.identityHashCode(proxy);
                if ("equals".equals(n)) return args != null && args.length == 1 && proxy == args[0];
                if ("toString".equals(n)) return "GoogleLoginCallback";
                if (over[0]) return null;
                if ("onResult".equals(n)) {
                    over[0] = true;
                    String tok = null;
                    try {
                        Object cred = Class.forName("androidx.credentials.GetCredentialResponse").getMethod("getCredential").invoke(args[0]);
                        Bundle data = (Bundle) Class.forName("androidx.credentials.Credential").getMethod("getData").invoke(cred);
                        try {
                            Class<?> g = Class.forName("com.google.android.libraries.identity.googleid.GoogleIdTokenCredential");
                            Object gc = g.getMethod("createFrom", Bundle.class).invoke(null, data);
                            tok = (String) g.getMethod("getIdToken").invoke(gc);
                        } catch (Throwable ignored) { }
                        if ((tok == null || tok.length() == 0) && data != null) tok = data.getString(KEY_ID_TOKEN);
                    } catch (Throwable ignored) { }
                    done(call, tok);
                } else if ("onError".equals(n)) {
                    over[0] = true;
                    String kind = args != null && args.length > 0 && args[0] != null ? args[0].getClass().getName() : "";
                    if (kind.contains("Cancellation")) cancelled(call);
                    else classic(call, act, clientId);   // no Google account on the phone yet, old Play services...
                }
                return null;
            }
        });
        Executor main = new Executor() {
            @Override public void execute(Runnable r) { new Handler(Looper.getMainLooper()).post(r); }
        };
        cmC.getMethod("getCredentialAsync", Context.class, Class.forName("androidx.credentials.GetCredentialRequest"), CancellationSignal.class, Executor.class, cbI)
            .invoke(cm, act, req, new CancellationSignal(), main, cb);
    }

    /* ---------- the older Google Sign-In screen ---------- */
    private void classic(PluginCall call, Activity act, String clientId) {
        try {
            Class<?> gsoC = Class.forName("com.google.android.gms.auth.api.signin.GoogleSignInOptions");
            Class<?> bC = Class.forName("com.google.android.gms.auth.api.signin.GoogleSignInOptions$Builder");
            Object b = bC.getConstructor(gsoC).newInstance(gsoC.getField("DEFAULT_SIGN_IN").get(null));
            bC.getMethod("requestIdToken", String.class).invoke(b, clientId);
            bC.getMethod("requestEmail").invoke(b);
            Object gso = bC.getMethod("build").invoke(b);
            Class<?> clC = Class.forName("com.google.android.gms.auth.api.signin.GoogleSignInClient");
            Object client = Class.forName("com.google.android.gms.auth.api.signin.GoogleSignIn").getMethod("getClient", Activity.class, gsoC).invoke(null, act, gso);
            try { clC.getMethod("signOut").invoke(client); } catch (Throwable ignored) { }   // so the list of accounts is shown every time
            Intent i = (Intent) clC.getMethod("getSignInIntent").invoke(client);
            startActivityForResult(call, i, "classicDone");
        } catch (Throwable t) {
            call.reject("Google sign-in is not available on this phone", "unavailable");
        }
    }

    @ActivityCallback
    private void classicDone(PluginCall call, ActivityResult result) {
        if (call == null) return;
        try {
            Intent data = result == null ? null : result.getData();
            Object task = Class.forName("com.google.android.gms.auth.api.signin.GoogleSignIn").getMethod("getSignedInAccountFromIntent", Intent.class).invoke(null, data);
            Object acct = Class.forName("com.google.android.gms.tasks.Task").getMethod("getResult").invoke(task);
            String tok = (String) Class.forName("com.google.android.gms.auth.api.signin.GoogleSignInAccount").getMethod("getIdToken").invoke(acct);
            done(call, tok);
        } catch (Throwable t) {
            // 12501 = the person closed the screen; 10 = this app's signing key is not registered in Firebase
            int code = statusOf(t);
            if (code == 12501 || (code < 0 && result != null && result.getResultCode() == Activity.RESULT_CANCELED)) cancelled(call);
            else call.reject("Google sign-in failed" + (code >= 0 ? " (" + code + ")" : ""), "google_" + (code >= 0 ? code : 0));
        }
    }

    private static int statusOf(Throwable t) {
        for (int i = 0; t != null && i < 6; i++, t = t.getCause()) {
            try {
                if (t.getClass().getName().endsWith("ApiException")) return (Integer) t.getClass().getMethod("getStatusCode").invoke(t);
            } catch (Throwable ignored) { }
        }
        return -1;
    }
}
'''

MAIN = r'''package com.sangam360.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(GoogleLoginPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
'''


def find_activity():
    for d, _, files in os.walk(os.path.join(APP, "src/main/java")):
        if "MainActivity.java" in files:
            return os.path.join(d, "MainActivity.java")
    return None


def strip(text, name):
    return re.sub(r"\n?// sangam-%s-start.*?// sangam-%s-end\n?" % (name, name), "\n", text, flags=re.S)


def remove():
    act = find_activity()
    if act:
        cur = open(act, encoding="utf-8").read()
        new = re.sub(r"[ \t]*registerPlugin\(GoogleLoginPlugin\.class\);\n", "", cur)
        if new != cur:
            open(act, "w", encoding="utf-8").write(new)
        p = os.path.join(os.path.dirname(act), "GoogleLoginPlugin.java")
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(GRADLE):
        g = open(GRADLE, encoding="utf-8").read()
        open(GRADLE, "w", encoding="utf-8").write(strip(g, "google"))
    print("google sign-in: taken out of this build")


def key_ok():
    """True when the signing key file opens with the password from the secrets. Prints its SHA-1 (needed once in Firebase)."""
    path = os.path.join(APP, "sangam360.keystore")
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        if os.path.exists(path):
            os.remove(path)
            print("signing: the KEYSTORE_BASE64 secret is not a key file (paste the whole line again) - a temporary key is used")
        else:
            print("signing: no key in this build (secret KEYSTORE_BASE64) - a temporary key is used")
        return False
    os.environ["KEYSTORE_PASSWORD"] = os.environ.get("KEYSTORE_PASSWORD", "").strip()
    if not os.environ.get("KEYSTORE_PASSWORD"):
        os.remove(path)
        print("signing: the secret KEYSTORE_PASSWORD is missing - a temporary key is used")
        return False
    try:
        r = subprocess.run(["keytool", "-list", "-v", "-keystore", path, "-storetype", "PKCS12", "-alias", "sangam360", "-storepass:env", "KEYSTORE_PASSWORD"],
                           capture_output=True, text=True, timeout=120)
    except Exception as e:
        print("signing: could not check the key (%s) - using it as it is" % e)
        return True
    if r.returncode != 0:
        os.remove(path)
        print("signing: the key and KEYSTORE_PASSWORD do not fit together (check both secrets) - a temporary key is used")
        return False
    for line in r.stdout.splitlines():
        if re.match(r"\s*SHA-?(1|256):", line):
            print("signing: " + line.strip())
    return True


def web_client():
    """The project's Google web client ID, and whether google-services.json fits this app."""
    p = os.path.join(APP, "google-services.json")
    if not os.path.exists(p):
        print("google sign-in: no google-services.json in the repository - the Google button stays hidden")
        return ""
    g = open(GRADLE, encoding="utf-8").read()
    m = re.search(r'applicationId\s+"([^"]+)"', g)
    app_id = m.group(1) if m else "com.sangam360.app"
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print("google sign-in: google-services.json cannot be read (%s) - building without it" % e)
        os.remove(p)
        return ""
    clients = j.get("client", [])
    mine = [c for c in clients if c.get("client_info", {}).get("android_client_info", {}).get("package_name") == app_id]
    if not mine:
        print("google sign-in: google-services.json is for another app id, not %s - building without it" % app_id)
        os.remove(p)
        return ""
    for c in mine + clients:
        pool = list(c.get("oauth_client", []))
        pool += c.get("services", {}).get("appinvite_service", {}).get("other_platform_oauth_client", [])
        for o in pool:
            if o.get("client_type") == 3 and o.get("client_id"):
                return o["client_id"]
    print("google sign-in: no web client ID in google-services.json yet (turn on Google under Authentication, add the SHA-1, then download the file again)")
    return ""


def main():
    if not os.path.exists(GRADLE):
        print("google sign-in: Android project not found - skipped")
        return
    if "--plain" in sys.argv:      # last fallback of the build: no Google sign-in and no own signing key
        remove()
        g = open(GRADLE, encoding="utf-8").read()
        open(GRADLE, "w", encoding="utf-8").write(strip(g, "signing"))
        print("signing: taken out of this build - a temporary key is used")
        return
    if "--remove" in sys.argv:
        remove()
        return
    g = open(GRADLE, encoding="utf-8").read()

    # 1. the app's own signing key
    g = strip(g, "signing")
    if key_ok():
        g += SIGN
        print("signing: this APK is signed with the app's own key")

    # 2. Google sign-in
    g = strip(g, "google")
    cid = web_client()
    act = find_activity()
    ok = False
    if cid and act:
        cur = open(act, encoding="utf-8").read()
        m = re.search(r"^\s*package\s+([\w.]+)\s*;", cur, re.M)
        pkg = m.group(1) if m else "com.sangam360.app"
        fix = lambda s: s.replace("package com.sangam360.app;", "package " + pkg + ";")
        if "GoogleLoginPlugin" in cur:
            ok = True
        elif "super.onCreate(" in cur:
            open(act, "w", encoding="utf-8").write(cur.replace("super.onCreate(", "registerPlugin(GoogleLoginPlugin.class);\n        super.onCreate(", 1))
            ok = True
        elif re.search(r"extends\s+BridgeActivity\s*\{\s*\}", cur):
            open(act, "w", encoding="utf-8").write(fix(MAIN))
            ok = True
        else:
            print("google sign-in: MainActivity has an unexpected shape - skipped")
        if ok:
            open(os.path.join(os.path.dirname(act), "GoogleLoginPlugin.java"), "w", encoding="utf-8").write(fix(PLUGIN))
            g += DEPS
            page = "www/index.html"
            if os.path.exists(page):
                h = open(page, encoding="utf-8").read()
                if "SANGAM_GOOGLE_CLIENT" not in h.split("</head>")[0]:
                    h = h.replace("</head>", "<script>window.SANGAM_GOOGLE_CLIENT=%s;</script></head>" % json.dumps(cid), 1)
                    open(page, "w", encoding="utf-8").write(h)
            print("google sign-in: added (web client ...%s)" % cid[-28:])
    open(GRADLE, "w", encoding="utf-8").write(g)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the build because of this optional part
        print("google sign-in: skipped -", e)
