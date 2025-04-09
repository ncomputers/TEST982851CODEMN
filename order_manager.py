import logging
import uuid
import time
import json
import redis
from exchange import DeltaExchangeClient
import config

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self):
        self.client = DeltaExchangeClient()
        self.orders = {}
        self.redis_client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB)

    def _store_order_in_redis(self, order_info):
        key = f"order:{order_info['id']}"
        self.redis_client.set(key, json.dumps(order_info))

    def is_order_open(self, symbol, side):
        # First, check actual open orders via API
        try:
            open_orders = self.client.exchange.fetch_open_orders(symbol)
            for order in open_orders:
                if order.get('side', '').lower() == side.lower() and order.get('status', '').lower() == 'open':
                    return True
        except Exception as e:
            logger.error("Error checking open orders via API: %s", e)

        # Fallback to local cache
        for order in self.orders.values():
            if order['symbol'] == symbol and order['side'].lower() == side.lower() and order['status'].lower() == 'open':
                return True
        return False

    def has_open_position(self, symbol, side):
        """
        Returns True if an actual position is open on the exchange.
        """
        try:
            positions = self.client.fetch_positions()
            for pos in positions:
                pos_symbol = (pos.get('info', {}).get('product_symbol') or pos.get('symbol') or '')
                if symbol not in pos_symbol:
                    continue
                size = pos.get('size') or pos.get('contracts') or 0
                try:
                    size = float(size)
                except Exception:
                    size = 0.0
                if side.lower() == "buy" and size > 0:
                    return True
                if side.lower() == "sell" and size < 0:
                    return True
        except Exception as e:
            logger.error("Error checking open positions via API: %s", e)
        return False

    def place_order(self, symbol, side, amount, price, params=None):
        try:
            order = self.client.create_limit_order(symbol, side, amount, price, params)
            order_id = order.get('id')
            if not order_id:
                order_id = int(time.time() * 1000)
            order_info = {
                'id': order_id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': price,
                'params': params or {},
                'status': order.get('status', 'open'),
                'timestamp': order.get('timestamp', int(time.time() * 1000))
            }
            self.orders[order_id] = order_info
            self._store_order_in_redis(order_info)
            logger.debug("Placed order: %s", order_info)
            return order_info
        except Exception as e:
            logger.error("Error placing order for %s: %s", symbol, e)
            raise

    def attach_bracket_to_order(self, order_id, product_id, product_symbol, bracket_params):
        try:
            exchange_order = self.client.modify_bracket_order(order_id, product_id, product_symbol, bracket_params)
            if order_id in self.orders:
                self.orders[order_id]['params'].update(bracket_params)
                self.orders[order_id]['status'] = exchange_order.get('state', self.orders[order_id]['status'])
                self._store_order_in_redis(self.orders[order_id])
                logger.debug("Attached bracket to order %s: %s", order_id, self.orders[order_id])
                return self.orders[order_id]
            else:
                order_info = {
                    'id': order_id,
                    'product_id': product_id,
                    'product_symbol': product_symbol,
                    'params': bracket_params,
                    'status': exchange_order.get('state', 'open'),
                    'timestamp': exchange_order.get('created_at', int(time.time() * 1000000))
                }
                self.orders[order_id] = order_info
                self._store_order_in_redis(order_info)
                logger.debug("Attached bracket to order (new record) %s: %s", order_id, order_info)
                return order_info
        except Exception as e:
            logger.error("Error attaching bracket to order %s: %s", order_id, e)
            raise

    def modify_bracket_order(self, order_id, new_bracket_params):
        if order_id not in self.orders:
            raise ValueError("Bracket order ID not found.")
        order = self.orders[order_id]
        order['params'].update(new_bracket_params)
        self._store_order_in_redis(order)
        logger.debug("Modified bracket order %s locally: %s", order_id, order)
        return order

    def cancel_order(self, order_id):
        if order_id not in self.orders:
            raise ValueError("Order ID not found.")
        order = self.orders[order_id]
        symbol = order.get('symbol') or order.get('product_symbol')
        try:
            result = self.client.cancel_order(order_id, symbol)
            order['status'] = 'canceled'
            self._store_order_in_redis(order)
            logger.debug("Canceled order %s: %s", order_id, result)
            return result
        except Exception as e:
            logger.error("Error canceling order %s: %s", order_id, e)
            raise

if __name__ == '__main__':
    om = OrderManager()
    try:
        limit_order = om.place_order("BTCUSD", "buy", 1, 45000)
        print("Limit order placed:", limit_order)
    except Exception as e:
        print("Failed to place limit order:", e)
        exit(1)

    bracket_params = {
        "bracket_stop_loss_limit_price": "50000",
        "bracket_stop_loss_price": "50000",
        "bracket_take_profit_limit_price": "55000",
        "bracket_take_profit_price": "55000",
        "bracket_stop_trigger_method": "last_traded_price"
    }
    try:
        updated_order = om.attach_bracket_to_order(
            order_id=limit_order['id'],
            product_id=27,
            product_symbol="BTCUSD",
            bracket_params=bracket_params
        )
        print("Bracket attached, updated order:", updated_order)
    except Exception as e:
        print("Failed to attach bracket to order:", e)