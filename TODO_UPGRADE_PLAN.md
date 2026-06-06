# Upgrade Plan: Smart News Sentiment Engine + Gemini CRO

## Phase 1: Upgrade "Smart" News Sentiment Engine
**File**: `engine/news_filter.py`
- Add import for get_news_sentiment from data.news
- Add `get_trading_bias(asset, headlines)` async method to NewsKillswitch class
- Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'

## Phase 2: Upgrade Gemini "Chief Risk Officer" (CRO)
**File**: `services/gemini_ml.py`
- Add new function `get_news_sentiment(asset, headlines)` that asks Gemini to classify news
- Update `gemini_confluence_check()` to accept `tech_context` dict parameter  
- Implement Chain-of-Thought (CoT) prompting

## Phase 3: "Golden Loop" Integration
**File**: `engine/core.py`
- Add helper functions to fetch market pulse (RSI, EMA trend, ATR)
- Integrate Gemini confluence validation in signal processing loop

## Dependent Files:
- engine/news_filter.py
- services/gemini_ml.py  
- engine/core.py
