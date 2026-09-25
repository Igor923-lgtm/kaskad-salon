import urllib.request, http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Login
login_data = b"password=hairos2026"
req = urllib.request.Request("http://localhost:8005/login", data=login_data, method="POST")
try:
    r = opener.open(req, timeout=5)
    print("Login:", r.getcode(), r.url)
except urllib.error.HTTPError as e:
    print("Login:", e.code, e.url)

# Check cookies
for c in cj:
    print("Cookie:", c.name, c.value[:20])

# Test pages with auth
tests = [
    ("Dashboard", "http://localhost:8005/dashboard"),
    ("Settings", "http://localhost:8005/settings"),
    ("Finance", "http://localhost:8005/finance"),
    ("Schedule", "http://localhost:8005/schedule"),
    ("Bookings", "http://localhost:8005/bookings"),
    ("Analytics", "http://localhost:8005/analytics"),
    ("Users", "http://localhost:8005/users"),
    ("Services", "http://localhost:8005/services"),
]

for name, url in tests:
    try:
        r = opener.open(url, timeout=5)
        body = r.read().decode()
        print("  " + name.ljust(15) + " HTTP " + str(r.getcode()) + "  (" + str(len(body)) + " bytes)")
    except urllib.error.HTTPError as e:
        print("  " + name.ljust(15) + " HTTP " + str(e.code))
    except Exception as e:
        print("  " + name.ljust(15) + " ERR " + str(e))
