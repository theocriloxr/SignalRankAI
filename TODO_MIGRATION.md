# TODO: Gemini SDK Migration (google-generativeai → google-genai)

## Status: COMPLETED ✅

### Steps:
- [x] 1. Update requirements.txt - Replace google-generativeai with google-genai
- [x] 2. Update services/gemini_ml.py - Migrate to new SDK
- [x] 3. Test the updated SDK

## Implementation Notes:
- Updated from `google.generativeai` with `GenerativeModel` and `generate_content_async()`
- Updated to: `google.genai` with `Client` and `client.models.generate_content()`
- Model: gemini-2.0-flash

## Verification Script:
```python
import asyncio
from services.gemini_ml import gemini_confluence_check

async def test_validator():
    # Test 1: Should likely Veto (Buying a crash)
    bad_signal = {'asset': 'BTC', 'direction': 'long'}
    bad_news = ["Bitcoin falls 10% as SEC announces new lawsuit", "Crypto exchange hacked"]
    
    # Test 2: Should likely Approve
    good_signal = {'asset': 'BTC', 'direction': 'short'}
    
    print(f"Test 1 (Should Veto): {await gemini_confluence_check(bad_signal, bad_news)}")
    print(f"Test 2 (Should Approve): {await gemini_confluence_check(good_signal, bad_news)}")

asyncio.run(test_validator())
