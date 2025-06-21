import sys
import os
import time
import shutil
import subprocess

old_exe, new_exe = sys.argv[1], sys.argv[2]

# Ждём, пока основной exe завершится
for _ in range(30):
    try:
        os.remove(old_exe)
        break
    except PermissionError:
        time.sleep(1)

# Копируем новый exe на место старого
shutil.move(new_exe, old_exe)

# Запускаем новый exe
subprocess.Popen([old_exe])
