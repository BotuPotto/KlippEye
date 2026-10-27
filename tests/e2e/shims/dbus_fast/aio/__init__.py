class ProxyInterface: pass
class MessageBus:
    connected = False
    def __init__(self, *a, **k): pass
    async def connect(self): raise RuntimeError("no dbus in sandbox")
