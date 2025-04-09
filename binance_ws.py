import json
import threading
import time
import websocket

# Global variable to store the latest BTC/USDT price
current_price = None

def on_message(ws, message):
    global current_price
    try:
        data = json.loads(message)
        # Ensure the necessary keys exist
        if "p" not in data or "q" not in data or "m" not in data:
            return
        trade_data = {
            "timestamp": time.time(),
            "price": float(data["p"]),
            "buy_qty": float(data["q"]) if not data["m"] else 0,
            "sell_qty": float(data["q"]) if data["m"] else 0
        }
        current_price = trade_data["price"]
    except Exception as e:
        print("Error processing message:", e)

def on_error(ws, error):
    print("WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed:", close_status_code, close_msg)

def on_open(ws):
    print("WebSocket connection opened")
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@aggTrade"],
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

def start_websocket():
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.on_open = on_open
    ws.run_forever()

def run_in_thread():
    """
    Start the Binance WebSocket in a separate thread.
    """
    websocket_thread = threading.Thread(target=start_websocket, daemon=True)
    websocket_thread.start()
    return websocket_thread

if __name__ == "__main__":
    run_in_thread()
    while True:
        if current_price is not None:
            print(f"Latest BTC/USDT price: {current_price}")
        time.sleep(2)
