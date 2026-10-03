@echo off
rem Daily MySQL backup for ip_inventory. Edit the three paths below if yours differ.
set MYSQLDUMP="C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"
set CNF=D:\IP_Inventory_Mgmt\backup.cnf
set OUT=D:\IP_Inventory_Backups

if not exist %OUT% mkdir %OUT%
for /f %%i in ('powershell -command "Get-Date -Format yyyyMMdd_HHmm"') do set STAMP=%%i

%MYSQLDUMP% --defaults-extra-file=%CNF% --single-transaction --no-tablespaces ip_inventory > %OUT%\ip_inventory_%STAMP%.sql

rem Keep 30 days of backups
forfiles /p %OUT% /m *.sql /d -30 /c "cmd /c del @path" 2>nul
