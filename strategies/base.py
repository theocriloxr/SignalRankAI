class BaseStrategy:
    name = "BASE"

    def evaluate(self, market_data):
        """
        Must return a strictly normalized, stateless, delivery-agnostic dict with at least:
            {
                'direction': 'long' | 'short',
                'confidence': float (0-1),
                'reasoning': str (human-readable explanation),
                'asset': str,
                'timeframe': str,
                'entry': float,
                'stop': float,
                'take_profit': float or list,
                'strategy_name': str,
                'strategy_group': str,
            }
        OR None
        - No delivery, user, Telegram, or tier logic allowed.
        - Must be pure/stateless and deterministic for same input.
        - All subclasses must implement this contract.
        """
        raise NotImplementedError
