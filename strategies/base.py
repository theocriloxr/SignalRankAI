class BaseStrategy:
    name = "BASE"

    def evaluate(self, market_data):
        """
        Must return a strictly normalized, stateless, delivery-agnostic dict:
        {
            'symbol': str,
            'direction': 'BUY' | 'SELL' | 'NEUTRAL',
            'timeframe': str,
            'entry': float,
            'stop': float,
            'targets': float or list,
            'confidence': float (0-1),
            'reasoning': str (human-readable explanation),
            ...
        }
        OR None
        - No delivery, user, Telegram, or tier logic allowed.
        - Must be pure/stateless and deterministic for same input.
        """
        raise NotImplementedError
