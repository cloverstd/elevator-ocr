from __future__ import annotations
from dataclasses import dataclass, field
from urllib.parse import urlparse

from paho.mqtt import client as mqtt_client

from app.config import Settings
from app.models import ElevatorStatePayload


@dataclass(slots=True)
class MqttPublisher:
    settings: Settings
    client: mqtt_client.Client | None = field(default=None, init=False)
    enabled: bool = field(default=True, init=False)

    def start(self) -> None:
        self.enabled = True
        parsed = urlparse(self.settings.mqtt_broker_url)
        if not parsed.hostname:
            self.enabled = False
            return

        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2,
            client_id=self.settings.mqtt_client_id,
        )
        port = parsed.port or 1883
        if parsed.username:
            client.username_pw_set(parsed.username, parsed.password)

        try:
            client.connect(parsed.hostname, port=port, keepalive=60)
            client.loop_start()
        except OSError:
            self.enabled = False
            return
        self.client = client

    def stop(self) -> None:
        if self.client is None:
            return
        self.client.loop_stop()
        self.client.disconnect()
        self.client = None

    def publish_state(self, payload: ElevatorStatePayload) -> None:
        if not self.enabled or self.client is None:
            return
        message = payload.model_dump_json()
        self.client.publish(
            self.settings.mqtt_topic_state,
            payload=message,
            qos=0,
            retain=True,
        )
