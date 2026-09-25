import urllib.request
import json

def test(name, url, expect=None):
    try:
        r = urllib.request.urlopen(url, timeout=5)
        body = r.read().decode()
        code = r.getcode()
        if expect and expect not in body:
            print("  " + name.ljust(25) + "WARN HTTP " + str(code) + " (" + str(len(body)) + "b) missing:" + expect[:30])
        else:
            print("  " + name.ljust(25) + "OK   HTTP " + str(code) + " (" + str(len(body)) + "b)")
    except urllib.error.HTTPError as e:
        print("  " + name.ljust(25) + "ERR  HTTP " + str(e.code))
    except Exception as e:
        print("  " + name.ljust(25) + "FAIL " + str(e)[:50])

def test_auth(name, url, cookie):
    try:
        req = urllib.request.Request(url)
        req.add_header("Cookie", cookie)
        r = urllib.request.urlopen(req, timeout=5)
        body = r.read().decode()
        print("  " + name.ljust(25) + "OK   HTTP " + str(r.getcode()) + " (" + str(len(body)) + "b)")
    except urllib.error.HTTPError as e:
        print("  " + name.ljust(25) + "ERR  HTTP " + str(e.code))
    except Exception as e:
        print("  " + name.ljust(25) + "FAIL " + str(e)[:50])

# === HAIROS ===
print("=== HAIROS (8005) ===")
test("Health", "http://localhost:8005/health", "ok")
test("Master login", "http://localhost:8005/master", "HairOS")
test("Master dashboard", "http://localhost:8005/master/dashboard", "master")
test("Widget", "http://localhost:8005/widget", "widget")
test("Masters page", "http://localhost:8005/masters")
test("Book page", "http://localhost:8005/book")
test("Login page", "http://localhost:8005/login", "Hairos")
test("API masters", "http://localhost:8005/api/masters", "name")
test("API services", "http://localhost:8005/api/services", "name")
test("API salon-hours", "http://localhost:8005/api/salon-hours")
test("Manifest", "http://localhost:8005/static/manifest.json", "icon-192.png?v=2")
test("Icon 192", "http://localhost:8005/static/icon-192.png?v=2")
test("Icon 512", "http://localhost:8005/static/icon-512.png?v=2")

# Auth test
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:
    req = urllib.request.Request("http://localhost:8005/login", data=b"password=hairos2026", method="POST")
    opener.open(req, timeout=5)
    cookie = "crm_token=" + [c.value for c in cj if c.name == "crm_token"][0]
    test_auth("Dashboard (auth)", "http://localhost:8005/dashboard", cookie)
    test_auth("Finance (auth)", "http://localhost:8005/finance", cookie)
    test_auth("Schedule (auth)", "http://localhost:8005/schedule", cookie)
    test_auth("Bookings (auth)", "http://localhost:8005/bookings", cookie)
    test_auth("Settings (auth)", "http://localhost:8005/settings", cookie)
    test_auth("Analytics (auth)", "http://localhost:8005/analytics", cookie)
    test_auth("Users (auth)", "http://localhost:8005/users", cookie)
    test_auth("Services (auth)", "http://localhost:8005/services", cookie)
except Exception as e:
    print("  AUTH FAILED:", e)

print()

# === KASKAD ===
print("=== KASKAD (8000) ===")
test("Health", "http://localhost:8000/health", "ok")
test("Master login", "http://localhost:8000/master", "HairOS")
test("Master dashboard", "http://localhost:8000/master/dashboard", "master")
test("Widget", "http://localhost:8000/widget", "widget")
test("Masters page", "http://localhost:8000/masters")
test("Book page", "http://localhost:8000/book")
test("Login page", "http://localhost:8000/login", "Kaskad")
test("API masters", "http://localhost:8000/api/masters", "name")
test("API services", "http://localhost:8000/api/services", "name")
test("API salon-hours", "http://localhost:8000/api/salon-hours")
test("Manifest", "http://localhost:8000/static/manifest.json", "icon-192.png?v=2")
test("Icon 192", "http://localhost:8000/static/icon-192.png?v=2")
test("Icon 512", "http://localhost:8000/static/icon-512.png?v=2")

cj2 = http.cookiejar.CookieJar()
opener2 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj2))
try:
    req = urllib.request.Request("http://localhost:8000/login", data=b"password=kaskad2026", method="POST")
    opener2.open(req, timeout=5)
    cookie = "crm_token=" + [c.value for c in cj2 if c.name == "crm_token"][0]
    test_auth("Dashboard (auth)", "http://localhost:8000/dashboard", cookie)
    test_auth("Finance (auth)", "http://localhost:8000/finance", cookie)
    test_auth("Schedule (auth)", "http://localhost:8000/schedule", cookie)
    test_auth("Bookings (auth)", "http://localhost:8000/bookings", cookie)
    test_auth("Settings (auth)", "http://localhost:8000/settings", cookie)
    test_auth("Analytics (auth)", "http://localhost:8000/analytics", cookie)
    test_auth("Users (auth)", "http://localhost:8000/users", cookie)
    test_auth("Services (auth)", "http://localhost:8000/services", cookie)
except Exception as e:
    print("  AUTH FAILED:", e)

print("\n=== DONE ===")
