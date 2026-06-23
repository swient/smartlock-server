import os
import uuid
import json
import base64
from typing import Any, List
from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app.models import SmartLock
from app.core.crypto import ServerCryptoManager
from app.core.mqtt import mqtt_service
from sqlmodel import select

router = APIRouter(prefix="/locks", tags=["smartlocks"])


@router.post("/initiate-bind", response_model=dict)
def initiate_bind(
    *,
    session: SessionDep,
    device_uuid: str,
    binding_key_hex: str,
    current_user: CurrentUser,
) -> Any:
    lock = session.exec(select(SmartLock).where(SmartLock.device_uuid == device_uuid)).first()

    if lock:
        if lock.is_bound:
            raise HTTPException(status_code=400, detail="此裝置已被綁定，無法重複綁定")
    else:
        lock = SmartLock(
            device_uuid=device_uuid,
            binding_key=binding_key_hex,
            is_bound=False,
        )
        session.add(lock)

    try:
        binding_key_bytes = bytes.fromhex(binding_key_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="設備綁定碼格式錯誤")

    srv_priv_bytes, srv_pub_bytes, srv_hmac_bytes = ServerCryptoManager.generate_ecdh_keys(binding_key_bytes)

    transaction_id = str(uuid.uuid4())

    lock.binding_key = binding_key_hex
    lock.user_id = current_user.id
    lock.last_transaction_id = transaction_id
    lock.temp_private_key = srv_priv_bytes.hex()
    session.add(lock)
    session.commit()

    req_payload = {
        "transaction_id": transaction_id,
        "public_key": base64.b64encode(srv_pub_bytes).decode("utf-8"),
        "hmac": base64.b64encode(srv_hmac_bytes).decode("utf-8"),
    }
    req_topic = f"device/smartlock/{device_uuid}/downlink/bind_req"
    mqtt_service.client.publish(req_topic, json.dumps(req_payload), qos=1)

    return {"status": "success", "message": "已向設備發送綁定請求，等待設備驗證回覆"}


@router.post("/{device_uuid}/unbind", response_model=dict)
def unbind_device(
    device_uuid: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    statement = select(SmartLock).where(SmartLock.device_uuid == device_uuid, SmartLock.user_id == current_user.id)
    lock = session.exec(statement).first()

    if not lock:
        raise HTTPException(status_code=404, detail="找不到該智慧鎖或您無權限操作")

    if not lock.is_bound:
        raise HTTPException(status_code=400, detail="該裝置目前本來就處於未綁定狀態")

    lock.is_bound = False
    lock.master_key = None
    lock.temp_private_key = None
    lock.last_transaction_id = None
    lock.user_id = None

    session.add(lock)
    session.commit()

    return {"status": "success", "message": "已成功解除綁定"}


@router.get("/{device_uuid}/logs", response_model=List[dict])
def get_lock_logs(
    device_uuid: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    statement = select(SmartLock).where(SmartLock.device_uuid == device_uuid, SmartLock.user_id == current_user.id)
    lock = session.exec(statement).first()

    if not lock or not lock.is_bound:
        raise HTTPException(status_code=404, detail="找不到該智慧鎖、尚未完成綁定或您無權限查看")

    return [
        {
            "timestamp": log.timestamp_ms,
            "authenticated": log.authenticated,
            "type": log.auth_type,
            "image": log.image_b64,
        }
        for log in lock.logs
    ]


@router.post("/{device_uuid}/unlock", response_model=dict)
def send_unlock_command(
    device_uuid: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    statement = select(SmartLock).where(SmartLock.device_uuid == device_uuid, SmartLock.user_id == current_user.id)
    lock = session.exec(statement).first()

    if not lock or not lock.is_bound or not lock.master_key:
        raise HTTPException(status_code=400, detail="裝置未完成綁定或您無權限操作")

    try:
        session_salt = os.urandom(16)
        master_key_bytes = bytes.fromhex(lock.master_key)

        session_key = ServerCryptoManager.derive_session_key(master_key_bytes, session_salt)

        command_payload = {
            "command_type": "UNLOCK",
            "command_payload": {},
        }
        plaintext = json.dumps(command_payload).encode("utf-8")

        ciphertext_with_nonce = ServerCryptoManager.encrypt_data(plaintext, session_key)

        mqtt_payload = {
            "session_salt": session_salt.hex(),
            "ciphertext": base64.b64encode(ciphertext_with_nonce).decode("utf-8"),
        }

        control_topic = f"device/smartlock/{device_uuid}/downlink/control"
        mqtt_service.client.publish(control_topic, json.dumps(mqtt_payload), qos=1)

        return {"status": "success", "message": "遠端開鎖指令已成功加密送出"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"開鎖指令封裝失敗: {str(e)}")
