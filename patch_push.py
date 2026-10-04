import re
p = "www/index.html"
s = open(p, encoding="utf-8").read()

fn = '''async function registerPush(){
 try{
  const C=window.Capacitor;if(!C||!C.isNativePlatform||!C.isNativePlatform())return;
  const PN=C.Plugins&&C.Plugins.PushNotifications;if(!PN)return;
  let p=await PN.checkPermissions();
  if(p.receive!=="granted")p=await PN.requestPermissions();
  if(p.receive!=="granted")return;
  if(!window.__pnInit){window.__pnInit=1;
   PN.addListener("registration",async t=>{try{await setDoc(doc(db,"societies",S.sid,"directory",S.uid),{uid:S.uid,fcm:t.value},{merge:true})}catch(e){console.error(e)}});
   PN.addListener("registrationError",e=>console.error(e));
  }
  await PN.register();
 }catch(e){console.error(e)}
}
'''
a = "function startApp(){"
b = 'listen();show("sMain");go("home");'
assert s.count(a) == 1, "startApp not found"
assert s.count(b) == 1, "listen call not found"
s = s.replace(a, fn + a)
s = s.replace(b, 'registerPush();' + b)
open(p, "w", encoding="utf-8").write(s)
print("patched ok")
