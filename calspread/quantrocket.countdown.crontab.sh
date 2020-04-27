# Crontab commands for calspread
# Intended to be run in timezone America/New_York

# Crontab syntax cheat sheet
# .------------ minute (0 - 59)
# |   .---------- hour (0 - 23)
# |   |   .-------- day of month (1 - 31)
# |   |   |   .------ month (1 - 12) OR jan,feb,mar,apr ...
# |   |   |   |   .---- day of week (0 - 6) (Sunday=0 or 7)  OR sun,mon,tue,wed,thu,fri,sat
# |   |   |   |   |
# *   *   *   *   *   command to be executed

# make sure IB Gateway is running each weekday
0 7 * * mon-fri quantrocket ibg start

# collect native combo data each morning
0 8 * * mon-fri quantrocket satellite exec 'codeload.calspread.collect_combo.collect_combo' --params 'universe:cl-fut' 'contract_months:[1,2]' 'tick_db:cl-combo-tick' 'until:16:30:00 America/New_York'

# Trade calspread-native-cl every minute from 9 AM to 4 PM. This command "paper trades" by logging orders to flightlog; to 
# live or paper trade with broker, send orders to blotter instead
* 9-15 * * mon-fri quantrocket moonshot trade 'calspread-native-cl' | quantrocket flightlog log -n 'quantrocket.moonshot'
