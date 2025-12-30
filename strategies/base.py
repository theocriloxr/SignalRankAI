class BaseStrategy:
    name = "BASE"

    def evaluate(self, market_data):
        """
        Must return:
        {
            symbol,
            direction,
            timeframe,
            entry,
            stop,
            targets,
            confidence
        }
        OR None
        """
        raise NotImplementedError
