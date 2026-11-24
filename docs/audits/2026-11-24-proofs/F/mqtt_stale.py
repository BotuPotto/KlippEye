"""Proof: (1) when Moonraker answers but Klipper is down (read_status -> None), the bridge publishes nothing, so the
retained 'printing' state stays on the broker; (2) two Pis with the default host name share one MQTT client id."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../backend"))
import mqtt_bridge

class FakeClient:
    connected = True
    def __init__(self): self.sent = []
    def publish(self, topic, payload, retain=False): self.sent.append((topic, payload)); return True

status = {"print_stats": {"state": "printing", "print_duration": 600}, "display_status": {"progress": 0.4},
          "extruder": {"temperature": 215, "target": 215}, "heater_bed": {"temperature": 60, "target": 60}, "webhooks": {"state": "ready"}}
answers = [status, None]
settings = mqtt_bridge.clean({"enabled": True, "host": "broker.local", "discovery": False})
bridge = mqtt_bridge.Bridge(settings, lambda objects: answers.pop(0), lambda: {}, lambda: [], None, None, lambda: {}, node="raspberrypi")
bridge.client = FakeClient()
bridge.lights_at = 1e18
bridge.tick(); first = len(bridge.client.sent)
bridge.tick()  # Klipper stopped: Moonraker's query fails
print("published while printing:", first, "| published once Klipper is down:", len(bridge.client.sent) - first,
      "| retained state left:", bridge.last["state"])
print("client id of two Pis named raspberrypi:", "klippeye-" + mqtt_bridge.node_id("raspberrypi"), "and", "klippeye-" + mqtt_bridge.node_id("raspberrypi"))
