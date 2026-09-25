import paramiko
import socket

SERVER = '45.159.172.228'
USER = 'root'
PASS = 'DndhJ98X1U8LZg24'

print(f"Подключение к {SERVER}...")

try:
    transport = paramiko.Transport((SERVER, 22))
    transport.connect(username=USER, password=PASS)
    print("OK транспорт подключен")

    session = transport.open_session()
    session.exec_command('uname -a')
    print("OK:", session.recv(1024).decode().strip())

    session.close()
    transport.close()

except paramiko.AuthenticationException as e:
    print(f"FAIL auth: {e}")
except paramiko.SSHException as e:
    print(f"FAIL ssh: {e}")
except socket.error as e:
    print(f"FAIL socket: {e}")
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")
