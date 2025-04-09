import time
import logging
import threading
import winsound
from exchange import DeltaExchangeClient
import config
import binance_ws  # Live price updates via WS
from trade_manager import TradeManager
from notifier import send_email

logger = logging.getLogger(__name__)

class ProfitTrailing:
    def __init__(self, check_interval):
        self.client = DeltaExchangeClient()
        self.trade_manager = TradeManager()
        self.check_interval = check_interval
        self.position_trailing_stop = {}
        self.last_had_positions = True
        self.last_position_fetch_time = 0
        self.position_fetch_interval = 5
        self.cached_positions = []
        self.last_error_email_sent = 0
        self.beep_thread = None
        self.beeping = False

    def start_beep_loop(self):
        def beep_loop():
            while self.beeping:
                winsound.Beep(1000, 1000)
                time.sleep(1)
        if not self.beeping:
            self.beeping = True
            self.beep_thread = threading.Thread(target=beep_loop, daemon=True)
            self.beep_thread.start()

    def stop_beep_loop(self):
        self.beeping = False

    def fetch_open_positions(self):
        try:
            positions = self.client.fetch_positions()
            self.stop_beep_loop()
            open_positions = []
            for pos in positions:
                size = pos.get('size') or pos.get('contracts') or 0
                try:
                    size = float(size)
                except Exception:
                    size = 0.0
                if size != 0:
                    pos_symbol = (pos.get('info', {}).get('product_symbol') or pos.get('symbol'))
                    if pos_symbol and "BTCUSD" in pos_symbol:
                        open_positions.append(pos)
            return open_positions
        except Exception as e:
            logger.error("Error fetching open positions: %s", e)
            if "ip_not_whitelisted" in str(e):
                current_time = time.time()
                self.start_beep_loop()
                if current_time - self.last_error_email_sent > 3600:
                    send_email(
                        subject="❌ IP Not Whitelisted for API Key",
                        body=f"The IP {e} is not authorized to access the API.",
                        to_email="rapidcorp.in@gmail.com"
                    )
                    self.last_error_email_sent = current_time
            else:
                if time.time() - self.last_error_email_sent > 3600:
                    send_email(
                        subject="⚠️ ProfitTrailing Error",
                        body=f"Unhandled error while fetching positions:\n{str(e)}",
                        to_email="rapidcorp.in@gmail.com"
                    )
                    self.last_error_email_sent = time.time()
            return []

    def compute_profit_pct(self, pos, live_price):
        entry = pos.get('entryPrice') or pos.get('entry_price') or pos.get('info', {}).get('entry_price')
        try:
            entry = float(entry)
        except Exception:
            return None
        size = pos.get('size') or pos.get('contracts') or 0
        try:
            size = float(size)
        except Exception:
            size = 0.0
        return (live_price - entry) / entry if size > 0 else (entry - live_price) / entry

    def get_trailing_config(self, profit_pct):
        conf = config.PROFIT_TRAILING_CONFIG
        if profit_pct < conf["start_trailing_profit_pct"]:
            return None
        applicable = None
        for level in conf["levels"]:
            if profit_pct >= level["min_profit_pct"]:
                applicable = level
        return applicable

    def update_trailing_stop(self, pos, live_price):
        order_id = pos.get('id')
        entry = pos.get('entryPrice') or pos.get('entry_price') or pos.get('info', {}).get('entry_price')
        try:
            entry = float(entry)
        except Exception:
            return None, None, None

        size = pos.get('size') or pos.get('contracts') or 0
        try:
            size = float(size)
        except Exception:
            size = 0.0

        profit_pct = self.compute_profit_pct(pos, live_price)
        if profit_pct is None:
            return None, None, None

        conf = config.PROFIT_TRAILING_CONFIG
        fixed_sl = conf["fixed_stop_loss_pct"]

        if profit_pct <= 0 or profit_pct < conf["start_trailing_profit_pct"]:
            rule = "fixed_stop"
            new_trailing = entry * (1 - fixed_sl) if size > 0 else entry * (1 + fixed_sl)
        else:
            level_conf = self.get_trailing_config(profit_pct)
            if level_conf is None:
                rule = "fixed_stop"
                new_trailing = entry * (1 - fixed_sl) if size > 0 else entry * (1 + fixed_sl)
            elif level_conf["trailing_stop_offset"] is not None:
                rule = "dynamic"
                new_trailing = entry * (1 + level_conf["trailing_stop_offset"]) if size > 0 else entry * (1 - level_conf["trailing_stop_offset"])
            else:
                rule = "partial_booking"
                book_fraction = level_conf.get("book_fraction", 1.0)
                new_trailing = entry * (1 + profit_pct * book_fraction) if size > 0 else entry * (1 - profit_pct * book_fraction)

        stored_trailing = self.position_trailing_stop.get(order_id)
        if stored_trailing is not None:
            new_trailing = max(stored_trailing, new_trailing) if size > 0 else min(stored_trailing, new_trailing)

        self.position_trailing_stop[order_id] = new_trailing
        return new_trailing, profit_pct, rule

    def compute_raw_profit(self, pos, live_price):
        entry = pos.get('entryPrice') or pos.get('entry_price') or pos.get('info', {}).get('entry_price')
        try:
            entry = float(entry)
        except Exception:
            return None
        size = pos.get('size') or pos.get('contracts') or 0
        try:
            size = float(size)
        except Exception:
            size = 0.0
        return (live_price - entry) * size if size > 0 else (entry - live_price) * abs(size)

    def book_profit(self, pos, live_price):
        order_id = pos.get('id')
        size = pos.get('size') or pos.get('contracts') or 0
        try:
            size = float(size)
        except Exception:
            size = 0.0

        trailing_stop, profit_pct, rule = self.update_trailing_stop(pos, live_price)
        logger.info("Order %s | Profit%%: %.2f%% | Rule: %s | Trailing Stop: %.4f | Live: %.2f",
                    order_id, profit_pct * 100 if profit_pct is not None else 0, rule, trailing_stop if trailing_stop else 0, live_price)

        if rule == "dynamic":
            if size > 0 and live_price < trailing_stop:
                logger.info("Trailing stop triggered for long order %s. Booking full profit.", order_id)
                close_order = self.trade_manager.place_market_order("BTCUSD", "sell", size, params={"time_in_force": "ioc"})
                logger.info("Market order to close long position placed: %s", close_order)
                return True
            elif size < 0 and live_price > trailing_stop:
                logger.info("Trailing stop triggered for short order %s. Booking full profit.", order_id)
                close_order = self.trade_manager.place_market_order("BTCUSD", "buy", abs(size), params={"time_in_force": "ioc"})
                logger.info("Market order to close short position placed: %s", close_order)
                return True
        elif rule == "partial_booking":
            logger.info("Partial booking mode for order %s. Updating bracket order to new trailing stop %.4f.", order_id, trailing_stop)
            try:
                bracket_params = {
                    "bracket_stop_loss_limit_price": str(trailing_stop),
                    "bracket_stop_loss_price": str(trailing_stop),
                    "bracket_stop_trigger_method": "last_traded_price"
                }
                updated_order = self.trade_manager.order_manager.attach_bracket_to_order(
                    order_id=order_id,
                    product_id=27,
                    product_symbol="BTCUSD",
                    bracket_params=bracket_params
                )
                logger.info("Bracket order updated for partial booking: %s", updated_order)
            except Exception as e:
                logger.error("Error updating bracket order for partial booking: %s", e)
            return False
        elif rule == "fixed_stop":
            if size > 0 and live_price < trailing_stop:
                logger.info("Fixed stop triggered for long order %s. Booking profit.", order_id)
                close_order = self.trade_manager.place_market_order("BTCUSD", "sell", size, params={"time_in_force": "ioc"})
                logger.info("Market order to close long position placed: %s", close_order)
                return True
            elif size < 0 and live_price > trailing_stop:
                logger.info("Fixed stop triggered for short order %s. Booking profit.", order_id)
                close_order = self.trade_manager.place_market_order("BTCUSD", "buy", abs(size), params={"time_in_force": "ioc"})
                logger.info("Market order to close short position placed: %s", close_order)
                return True
        return False

    def track(self):
        binance_ws.run_in_thread()
        wait_time = 0
        while binance_ws.current_price is None and wait_time < 30:
            print("Waiting for live price update...")
            time.sleep(2)
            wait_time += 2
        if binance_ws.current_price is None:
            print("Live price still not available. Exiting Profit Trailing Tracker.")
            return

        last_verification = time.time()
        while True:
            current_time = time.time()
            if current_time - self.last_position_fetch_time >= self.position_fetch_interval:
                self.cached_positions = self.fetch_open_positions()
                self.last_position_fetch_time = current_time
                if not self.cached_positions:
                    self.position_trailing_stop.clear()

            live_price = binance_ws.current_price
            if live_price is None:
                print("Live price not available.")
            else:
                open_positions = self.cached_positions
                has_positions = bool(open_positions)
                if not has_positions:
                    if self.last_had_positions:
                        print("No open positions. Profit trailing paused.")
                        self.last_had_positions = False
                    self.position_trailing_stop.clear()
                else:
                    if not self.last_had_positions:
                        print("Positions found. Profit trailing resumed.")
                        self.last_had_positions = True

                    for pos in open_positions:
                        order_id = pos.get('id')
                        size = pos.get('size') or pos.get('contracts') or 0
                        try:
                            size = float(size)
                        except Exception:
                            size = 0.0
                        if size == 0:
                            continue
                        entry = pos.get('entryPrice') or pos.get('entry_price') or pos.get('info', {}).get('entry_price')
                        try:
                            entry_val = float(entry)
                        except Exception:
                            entry_val = None
                        profit_pct = self.compute_profit_pct(pos, live_price)
                        profit_display = profit_pct * 100 if profit_pct is not None else None
                        raw_profit = self.compute_raw_profit(pos, live_price)
                        profit_usd = raw_profit / 1000 if raw_profit is not None else None
                        profit_inr = profit_usd * 85 if profit_usd is not None else None

                        trailing_stop, max_profit_pct, rule = self.update_trailing_stop(pos, live_price)
                        print(f"Order: {order_id} | Size: {size} | Entry: {entry_val} | Live: {live_price} | "
                              f"Profit%%: {profit_display:.4f}% | Profit (USD): {profit_usd:.4f} | "
                              f"Profit (INR): {profit_inr:.4f} | Rule: {rule} | Trailing Stop: {trailing_stop}")

                        if self.book_profit(pos, live_price):
                            print(f"Profit booked for order {order_id}.")

            time.sleep(self.check_interval)

if __name__ == '__main__':
    pt = ProfitTrailing(check_interval=1)
    pt.track()