# Phase 1 Implementation Todo

## Status: IN PROGRESS

### Feature 1: Signal Quality Assurance Layer (Historical Similarity)
- [ ] Create engine/similarity.py
- [ ] Add historical match scoring function
- [ ] Integrate with core.py pipeline
- [ ] Test similarity matching

### Feature 2: AI Market Memory Engine
- [ ] Create engine/market_memory.py
- [ ] Add memory storage functions
- [ ] Create DB tables if needed
- [ ] Integrate with signal storage

### Feature 3: Smart Asset Ranking
- [ ] Enhance engine/ranking.py
- [ ] Add opportunity scores
- [ ] Compute allocation weights
- [ ] Test ranking

### Feature 4: Dynamic Strategy Weighting
- [ ] Create engine/strategy_router.py
- [ ] Add regime-based selection
- [ ] Integrate with signal generation
- [ ] Test strategy routing

---

## Implementation Order:
1. similarity.py - Historical Similarity
2. market_memory.py - Memory Storage  
3. strategy_router.py - Strategy Router
4. ranking.py - Asset Ranking

## Dependencies:
- engine/core.py - Main pipeline
- engine/scoring.py - Scoring
- db/models.py - Database

## Notes:
- Start with simple implementations
- Build on existing infrastructure
- Test incrementally
