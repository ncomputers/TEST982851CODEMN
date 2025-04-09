import time
import logging
import uuid
import redis
from exchange import DeltaExchangeClient
from order_manager import OrderManager
import config

logger = logging.getLogger(__name__)

TOLERANCE = 1e-6  # Treat absolute sizes below this as zero.

class TradeManager:
    def __init__(self):
        self.client = DeltaExchangeClient()
        self.order_manager = OrderManager()
        self.highest_price = None

    def get_current_price(self, product_symbol):
        try:
            ticker = self.client.exchange.fetch_ticker(product_symbol)
            price = ticker.get('last')
            return float(price)
        except Exception as e:
            logger.error("Error fetching current price for %s: %s", product_symbol, e)
            raise

    def monitor_trailing_stop(self, bracket_order_id, product_symbol, trailing_stop_percent, update_interval=10):
        logger.info("Starting trailing stop monitoring for %s", product_symbol)
        self.highest_price = self.get_current_price(product_symbol)
        logger.info("Initial highest price: %s", self.highest_price)
        while True:
            try:
                current_price = self.get_current_price(product_symbol)
            except Exception as e:
                logger.error("Error fetching price, retrying: %s", e)
                time.sleep(update_interval)
                continue

            if current_price > self.highest_price:
                self.highest_price = current_price
                logger.info("New highest price: %s", self.highest_price)
            new_stop_loss = self.highest_price * (1 - trailing_stop_percent / 100.0)
            logger.info("Current price: %.2f, Calculated new stop loss: %.2f", current_price, new_stop_loss)
            new_stop_loss_order = {
                "order_type": "limit_order",
                "stop_price": str(round(new_stop_loss, 2)),
                "limit_price": str(round(new_stop_loss * 0.99, 2))
            }
            try:
                modified_order = self.order_manager.modify_bracket_order(
                    bracket_order_id, new_stop_loss_order=new_stop_loss_order
                )
                logger.info("Modified bracket order: %s", modified_order)
            except Exception as e:
                logger.error("Error modifying bracket order: %s", e)
            time.sleep(update_interval)

    def place_market_order(self, symbol, side, amount, params=None):
        """
        Before placing a new market order, verify via the API whether any open position or pending order exists
        for the given symbol and side. We clean up stale local orders before checking the local cache.
        If a pending order of the same side is detected, we simply skip the new signal.
        """
        side_lower = side.lower()

        # 1. Confirm open position via API (only for positions matching the symbol).
        try:
            positions = self.client.fetch_positions()
            for pos in positions:
                # Filter by symbol: check pos's symbol or product_symbol.
                pos_symbol = (pos.get('info', {}).get('product_symbol') or pos.get('symbol') or '')
                if symbol not in pos_symbol:
                    continue  # Ignore positions for other symbols.
                size = pos.get('size') or pos.get('contracts') or 0
                try:
                    size = float(size)
                except Exception:
                    size = 0.0
                # Apply tolerance to treat near-zero as zero.
                if abs(size) < TOLERANCE:
                    size = 0.0
                # For a buy signal (long), check if any positive size exists.
                if side_lower == "buy" and size > 0:
                    logger.info("An open buy position exists (confirmed by API) for %s. Skipping new order placement.", symbol)
                    return None
                # For a sell signal (short), check if any negative size exists.
                if side_lower == "sell" and size < 0:
                    logger.info("An open sell position exists (confirmed by API) for %s. Skipping new order placement.", symbol)
                    return None
        except Exception as e:
            logger.error("Error fetching positions from API: %s", e)
            # Optionally, decide how to proceed if this API check fails.

        # 2. Confirm pending orders via API.
        try:
            open_orders = self.client.exchange.fetch_open_orders(symbol)
            if open_orders:
                for o in open_orders:
                    if o.get('side', '').lower() == side_lower:
                        logger.info("An open %s order exists according to API for %s. Skipping new order placement.", side, symbol)
                        return None
            else:
                logger.info("No pending orders found via API for %s", symbol)
        except Exception as e:
            logger.error("Error fetching open orders from API: %s", e)
            # If this API check fails, we fall back to the local order cache below.

        # 3. Fallback: clean and check local pending orders stored in order_manager.
        current_time = int(time.time() * 1000)
        stale_order_ids = []
        for oid, order in self.order_manager.orders.items():
            order_ts = order.get('timestamp', 0)
            if current_time - order_ts > 60000:  # 60 seconds threshold for staleness.
                stale_order_ids.append(oid)
        for oid in stale_order_ids:
            del self.order_manager.orders[oid]
        
        for order in self.order_manager.orders.values():
            if order.get('side', '').lower() == side_lower and order.get('status') in ['open', 'pending']:
                logger.info("A local %s order is already pending for %s. Skipping new order placement (not canceling it).", side, symbol)
                return None

        # 4. No open position or pending order confirmed – place new market order.
        try:
            order = self.client.exchange.create_order(symbol, 'market', side, amount, None, params or {})
            order_id = order.get('id', str(uuid.uuid4()))
            order_info = {
                'id': order_id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'params': params or {},
                'status': order.get('status', 'open'),
                'timestamp': order.get('timestamp', int(time.time() * 1000))
            }
            self.order_manager.orders[order_id] = order_info
            self.order_manager._store_order_in_redis(order_info)

            # 5. Optionally verify with API after a brief delay.
            time.sleep(1)
            positions_after = self.client.fetch_positions()
            for pos in positions_after:
                pos_symbol = (pos.get('info', {}).get('product_symbol') or pos.get('symbol') or '')
                if symbol not in pos_symbol:
                    continue
                size = pos.get('size') or pos.get('contracts') or 0
                try:
                    size = float(size)
                except Exception:
                    size = 0.0
                if abs(size) < TOLERANCE:
                    size = 0.0
                if side_lower == "buy" and size > 0:
                    logger.info("Verified open buy position after order placement for %s.", symbol)
                    break
                if side_lower == "sell" and size < 0:
                    logger.info("Verified open sell position after order placement for %s.", symbol)
                    break

            logger.info("Market order placed: %s", order_info)
            return order_info
        except Exception as e:
            logger.error("Error placing market order for %s: %s", symbol, e)
            raise

if __name__ == '__main__':
    tm = TradeManager()
    print("Testing market order placement...")
    try:
        market_order = tm.place_market_order("BTCUSD", "buy", 1, params={"time_in_force": "ioc"})
        print("Market order placed:", market_order)
    except Exception as e:
        print("Failed to place market order:", e)
