import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Read schedule.html
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/templates/schedule.html")
content = stdout.read().decode('utf-8')

# Replace saveSchedModal function
old_func = '''async function saveSchedModal() {
  const masterName = document.getElementById('schedMasterName').value;
  const date = document.getElementById('schedDate').value;
  const isDayOff = document.getElementById('schedDayOff').checked;

  let slots = [];
  if (!isDayOff) {
    document.querySelectorAll('#schedSlotsGrid input[type="checkbox"]:checked').forEach(cb => {
      slots.push(cb.value);
    });
  }

  // Используем API для сохранения (нужен токен админа)
  // Пока сохраняем через master_schedule API
  const dow = new Date(date + 'T00:00:00').getDay();
  const dowAdj = dow === 0 ? 6 : dow - 1;

  if (isDayOff) {
    // Устанавливаем выходной через schedule API
    await fetch(`/api/schedule/${encodeURIComponent(masterName)}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify([{
        day_of_week: dowAdj,
        start_time: '10:00',
        end_time: '20:00',
        is_day_off: true
      }])
    });
  } else if (slots.length > 0) {
    // Сохраняем выбранные окошки через hours API
    // Для этого нужен токен - используем admin endpoint
    await fetch(`/api/admin/date-schedule?token=${localStorage.getItem('master_token') || ''}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        master_name: masterName,
        date: date,
        time_slots: slots,
        is_day_off: false
      })
    });
  }

  closeScheduleModal();
  loadDay();
}'''

new_func = '''async function saveSchedModal() {
  const masterName = document.getElementById('schedMasterName').value;
  const date = document.getElementById('schedDate').value;
  const isDayOff = document.getElementById('schedDayOff').checked;

  let slots = [];
  if (!isDayOff) {
    document.querySelectorAll('#schedSlotsGrid input[type="checkbox"]:checked').forEach(cb => {
      slots.push(cb.value);
    });
  }

  // Сохраняем через schedule API (не требует админа)
  const dow = new Date(date + 'T00:00:00').getDay();
  const dowAdj = dow === 0 ? 6 : dow - 1;

  if (isDayOff) {
    await fetch(`/api/schedule/${encodeURIComponent(masterName)}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify([{
        day_of_week: dowAdj,
        start_time: '10:00',
        end_time: '20:00',
        is_day_off: true
      }])
    });
  } else {
    // Сначала убираем выходной для этого дня недели
    await fetch(`/api/schedule/${encodeURIComponent(masterName)}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify([{
        day_of_week: dowAdj,
        start_time: '10:00',
        end_time: '20:00',
        is_day_off: false
      }])
    });
    // Если выбраны конкретные окошки — сохраняем их
    if (slots.length > 0) {
      await fetch(`/api/schedule/${encodeURIComponent(masterName)}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify([{
          day_of_week: dowAdj,
          start_time: '10:00',
          end_time: '20:00',
          is_day_off: false,
          selected_hours: slots.join(',')
        }])
      });
    }
  }

  closeScheduleModal();
  loadDay();
}'''

content = content.replace(old_func, new_func)

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/templates/schedule.html', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()

print("saveSchedModal fixed")

# Restart CRM
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot')
stdout.channel.recv_exit_status()
print("CRM restarted")

ssh.close()
print("Done!")
