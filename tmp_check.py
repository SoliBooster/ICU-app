import sys
sys.path.insert(0, '/home/jarryyansir/workspace-c707c28a-9d95-41c3-995c-741268b278d8')
try:
    from app import app
    print("APP IMPORT OK")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
