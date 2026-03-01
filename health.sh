#!/bin/bash
# health.sh — System health check
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 monitor.py dashboard
