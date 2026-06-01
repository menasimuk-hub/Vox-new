#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('dev.db')
result = conn.execute('SELECT value FROM settings WHERE key="telnyx_api_key" LIMIT 1').fetchone()
if result:
    api_key = result[0]
    print(f"API Key: {api_key}")
else:
    print("No Telnyx API key found")
