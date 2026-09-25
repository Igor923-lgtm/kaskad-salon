import sqlite3
db = sqlite3.connect('bot_cache.db')
c = db.cursor()
c.execute('SELECT id,master_name,service_name,client_name,client_phone,date,price,confirmed,completed,cancelled FROM bookings ORDER BY id DESC LIMIT 15')
print('BOOKINGS:')
for r in c.fetchall():
    print(r)
c.execute('SELECT telegram_id,name,phone,visit_count FROM clients')
print('CLIENTS:')
for r in c.fetchall():
    print(r)
c.execute('SELECT COUNT(*) FROM bookings')
print('Total bookings:', c.fetchone()[0])
c.execute('SELECT COUNT(*) FROM clients')
print('Total clients:', c.fetchone()[0])
db.close()
