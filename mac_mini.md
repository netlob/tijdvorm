# Disable all sleep

sudo pmset -a sleep 0
sudo pmset -a disablesleep 1
sudo pmset -a hibernatemode 0
sudo pmset -a autopoweroff 0
sudo pmset -a standby 0

sudo pmset -a displaysleep 0
sudo pmset -a powernap 0

# Verify

pmset -g

# docker compose up -d --build --force-recreate
