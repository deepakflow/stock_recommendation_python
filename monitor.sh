#!/bin/bash

# Memory and performance monitoring script

echo "📊 Stock Recommendation Agent - System Monitor"
echo "=============================================="

# Memory usage
echo "💾 Memory Usage:"
free -h
echo ""

# Application memory
echo "�� Application Memory:"
if pgrep -f "stock-recommendation" > /dev/null; then
    PID=$(pgrep -f "stock-recommendation")
    echo "Process ID: $PID"
    ps -o pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -10
else
    echo "Application not running"
fi
echo ""

# Disk usage
echo "�� Disk Usage:"
df -h /var/www/stock-recommendation-agent
echo ""

# Service status
echo "🔧 Service Status:"
systemctl status stock-recommendation --no-pager -l
echo ""

# Recent logs
echo "📝 Recent Logs:"
journalctl -u stock-recommendation -n 10 --no-pager
echo ""

# Network connections
echo "🌐 Network Connections:"
netstat -tlnp | grep :8000
echo ""

# Load average
echo "⚡ System Load:"
uptime
echo ""
