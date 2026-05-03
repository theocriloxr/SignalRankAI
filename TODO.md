# TODO: SignalRankAI Implementation Tasks

## ✅ COMPLETED
- [x] Fix KeyError: 'sqlalchemy' startup crash - moved SQLAlchemy import to first line in railway_main.py

## 🔄 IN PROGRESS
- [ ] Auto-adjusted confidence thresholds by Gemini/ML
- [ ] Generate signals consistently - not stop after one signal

## 📋 BACKLOG
- [ ] Integrate ML-driven confidence threshold adjustments
- [ ] Continuous signal generation (not one-shot)
- [ ] Performance metrics tracking (win rate, ROI, risk:reward ratio)

## Plan

### 1. Auto-adjusted Confidence Thresholds
- Create a new module in `engine/` or update `services/gemini_ml.py` to:
  - Analyze outcome data after each cycle
  - Calculate performance metrics (win rate, ROI, risk:reward)
  - Adjust ML_PROB_THRESHOLD dynamically
  - Persist thresholds in runtime_state

### 2. Continuous Signal Generation  
- Modify `engine/core.py` or `engine/loop.py`:
  - Ensure complete cycle runs for all assets
  - Don't exit after first signal found
  - Process entire asset batch each cycle

### 3. Performance Metrics Integration
- Track in `services/gemini_ml.py` or create new tracking jobs
- Store in runtime_state
- Use for threshold adjustment
