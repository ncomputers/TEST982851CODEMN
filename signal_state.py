import redis
import config

r = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB)

def set_last_sl_closed_side(side):
    r.set("last_sl_closed_side", side)

def get_last_sl_closed_side():
    value = r.get("last_sl_closed_side")
    return value.decode() if value else None

def clear_last_sl_closed_side():
    r.delete("last_sl_closed_side")
