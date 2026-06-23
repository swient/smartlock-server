import os
import json
import base64
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from sqlmodel import Session, select
from app.core.db import engine
from app.models import SmartLock, AuthLog
from app.core.crypto import ServerCryptoManager

load_dotenv()


class MQTTService:
    def __init__(self):
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")
        self.client = mqtt.Client(client_id="fastapi-backend-server")
        self.client.username_pw_set(username=username, password=password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.client.subscribe("device/smartlock/+/uplink/+")
            print("MQTT Connected and Subscribed to uplinks.")

    def _on_message(self, client, userdata, msg):
        topic_layers = msg.topic.split("/")
        device_uuid = topic_layers[2]
        action_type = topic_layers[4]
        payload = json.loads(msg.payload.decode("utf-8"))

        with Session(engine) as session:
            statement = select(SmartLock).where(SmartLock.device_uuid == device_uuid)
            lock = session.exec(statement).first()
            if not lock:
                return

            if action_type == "bind_res":
                self._handle_bind_res(session, lock, payload)
            elif action_type == "logs":
                self._handle_logs(session, lock, payload)

    def _handle_bind_res(self, session, lock, payload):
        if lock.is_bound:
            print(f"Device {lock.device_uuid} is already bound, ignoring bind_res.")
            return

        try:
            transaction_id = payload.get("transaction_id")
            if not transaction_id or lock.last_transaction_id != transaction_id:
                print(f"Transaction ID mismatch or missing for {lock.device_uuid}.")
                return

            binding_key_bytes = bytes.fromhex(lock.binding_key)
            temp_priv_bytes = bytes.fromhex(lock.temp_private_key)
            pi_public_bytes = base64.b64decode(payload["public_key"])
            pi_hmac_bytes = base64.b64decode(payload["hmac"])

            master_key = ServerCryptoManager.derive_master_key(
                pi_public_bytes, pi_hmac_bytes, temp_priv_bytes, binding_key_bytes
            )

            if not master_key:
                raise Exception("Failed to derive master key or HMAC verification failed")

            lock.master_key = master_key.hex()
            lock.is_bound = True
            lock.last_transaction_id = None
            lock.temp_private_key = None
            session.add(lock)
            session.commit()
            print(f"Device {lock.device_uuid} successfully bound! Master key derived.")

            ack_topic = f"device/smartlock/{lock.device_uuid}/downlink/bind_ack"
            ack_payload = {"transaction_id": transaction_id, "status": "success"}
            self.client.publish(ack_topic, json.dumps(ack_payload), qos=1)

        except Exception as e:
            print(f"Error processing bind_res for {lock.device_uuid}: {e}")
            lock.temp_private_key = None
            session.add(lock)
            session.commit()

    def _handle_logs(self, session, lock, payload):
        try:
            if not lock.master_key:
                return

            master_key_bytes = bytes.fromhex(lock.master_key)
            session_salt_bytes = bytes.fromhex(payload["session_salt"])
            ciphertext_bytes = base64.b64decode(payload["ciphertext"])

            session_key = ServerCryptoManager.derive_session_key(master_key_bytes, session_salt_bytes)

            plaintext_bytes = ServerCryptoManager.decrypt_data(ciphertext_bytes, session_key)
            if not plaintext_bytes:
                print(f"Decryption failed for logs from {lock.device_uuid}")
                return

            logs_data = json.loads(plaintext_bytes.decode("utf-8"))

            for log_entry in logs_data:
                existing = session.exec(
                    select(AuthLog).where(
                        AuthLog.smart_lock_id == lock.id, AuthLog.timestamp_ms == log_entry["timestamp_ms"]
                    )
                ).first()

                if existing:
                    continue

                log = AuthLog(
                    timestamp_ms=log_entry["timestamp_ms"],
                    authenticated=log_entry["authenticated"],
                    auth_type=log_entry["auth_type"],
                    confidence=log_entry["confidence"],
                    image_b64=log_entry["image"],
                    smart_lock_id=lock.id,
                )
                session.add(log)

            session.commit()
            print(f"Processed {len(logs_data)} logs for device {lock.device_uuid}")
        except Exception as e:
            print(f"Failed to process sync logs: {e}")

    def start(self):
        host = str(os.getenv("MQTT_BROKER_HOST"))
        port = int(os.getenv("MQTT_BROKER_PORT", 1883))
        self.client.connect(host, port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()


mqtt_service = MQTTService()
