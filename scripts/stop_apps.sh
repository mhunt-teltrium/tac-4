#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Stopping Natural Language SQL Interface...${NC}"

# Kill any running start.sh processes
echo -e "${GREEN}Killing start.sh processes...${NC}"
pkill -f "start.sh" 2>/dev/null

# Kill webhook server
echo -e "${GREEN}Killing webhook server...${NC}"
pkill -f "trigger_webhook.py" 2>/dev/null

# Kill processes on specific ports
echo -e "${GREEN}Killing processes on ports 5173, 8000, and 8001...${NC}"
powershell.exe -NoProfile -Command 'Get-NetTCPConnection -LocalPort 5173,8000,8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }'

echo -e "${GREEN}✓ Services stopped successfully!${NC}"