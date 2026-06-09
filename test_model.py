# Test the EconomicEvent model
import sys
sys.path.insert(0, '.')

try:
    from db.models import EconomicEvent
    print('✓ EconomicEvent model imported OK')
    attrs = [a for a in dir(EconomicEvent) if not a.startswith('_')]
    print(f'Attributes: {attrs}')
except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()
