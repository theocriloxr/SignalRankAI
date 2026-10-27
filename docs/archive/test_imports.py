"""Quick test script to validate imports"""
import sys
sys.path.insert(0, 'c:/Users/sammm/Desktop/SignalRankAI')

try:
    import data.providers
    print("data.providers: OK")
except Exception as e:
    print(f"data.providers: FAILED - {e}")

try:
    import data.news
    print("data.news: OK")
except Exception as e:
    print(f"data.news: FAILED - {e}")

try:
    import db.models
    print("db.models: OK")
except Exception as e:
    print(f"db.models: FAILED - {e}")

try:
    import engine.news_filter
    print("engine.news_filter: OK")
except Exception as e:
    print(f"engine.news_filter: FAILED - {e}")

try:
    import engine.core
    print("engine.core: OK")
except Exception as e:
    print(f"engine.core: FAILED - {e}")

try:
    import main
    print("main: OK")
except Exception as e:
    print(f"main: FAILED - {e}")

try:
    import railway_main
    print("railway_main: OK")
except Exception as e:
    print(f"railway_main: FAILED - {e}")

try:
    import worker.worker
    print("worker.worker: OK")
except Exception as e:
    print(f"worker.worker: FAILED - {e}")

print("\nAll imports tested!")
