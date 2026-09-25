import urllib.request

pages = [
    ("Health", "http://localhost:8005/health"),
    ("Dashboard", "http://localhost:8005/dashboard"),
    ("Settings", "http://localhost:8005/settings"),
    ("Finance", "http://localhost:8005/finance"),
    ("Schedule", "http://localhost:8005/schedule"),
    ("Masters", "http://localhost:8005/masters"),
    ("Widget", "http://localhost:8005/widget"),
    ("Book", "http://localhost:8005/book"),
    ("Bookings", "http://localhost:8005/bookings"),
    ("Login", "http://localhost:8005/login"),
    ("Master", "http://localhost:8005/master"),
    ("Analytics", "http://localhost:8005/analytics"),
    ("Users", "http://localhost:8005/users"),
    ("Services", "http://localhost:8005/services"),
    ("API services", "http://localhost:8005/api/services"),
    ("API masters", "http://localhost:8005/api/masters"),
    ("API bookings", "http://localhost:8005/api/bookings/grouped"),
]

for name, url in pages:
    try:
        r = urllib.request.urlopen(url, timeout=5)
        body = r.read().decode()
        code = r.getcode()
        print("  " + name.ljust(20) + " HTTP " + str(code).ljust(3) + "  (" + str(len(body)).rjust(6) + " bytes)")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:80]
        print("  " + name.ljust(20) + " HTTP " + str(e.code).ljust(3) + "  " + body[:60])
    except Exception as e:
        print("  " + name.ljust(20) + " ERROR  " + str(e))
