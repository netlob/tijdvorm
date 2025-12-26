#!/bin/bash
# Debug script for Tijdvorm Streamer
# Usage: ./debug.sh [command]
# Commands:
#   start     - Start the streamer
#   test      - Test display with a sample URL
#   stop      - Stop display
#   status    - Check if streamer is running
#   logs      - Show recent logs
#   net       - Show network ports in use

STREAMER_HOST="${STREAMER_HOST:-http://localhost:8008}"

case "$1" in
    start)
        echo "Starting streamer..."
        ./run.sh &
        sleep 2
        echo "Streamer started. Check $STREAMER_HOST/health"
        ;;
    test)
        echo "Testing display with sample URL..."
        curl -X POST "$STREAMER_HOST/display" \
             -H "Content-Type: application/json" \
             -d '{"url": "http://www.example.com"}'
        echo ""
        ;;
    stop)
        echo "Stopping display..."
        curl -X POST "$STREAMER_HOST/stop"
        echo ""
        ;;
    status)
        echo "Checking streamer status..."
        curl -s "$STREAMER_HOST/health" || echo "Streamer not responding"
        ;;
    logs)
        echo "Recent logs:"
        tail -20 ~/.local/share/tijdvorm/streamer.log 2>/dev/null || echo "No logs found"
        ;;
    net)
        echo "Network ports in use:"
        sudo netstat -tuln | grep -E "(8008|8090|19444)" || echo "Ports not in use"
        ;;
    *)
        echo "Usage: $0 {start|test|stop|status|logs|net}"
        echo "Environment:"
        echo "  STREAMER_HOST=$STREAMER_HOST"
        ;;
esac
