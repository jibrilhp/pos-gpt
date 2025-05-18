import re
import qrcode
import base64
from io import BytesIO

def convert_crc16(qris_str):
    def char_code_at(s, idx): return ord(s[idx])
    crc = 0xFFFF
    for c in qris_str:
        crc ^= ord(c) << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if (crc & 0x8000) else (crc << 1)
    return "{:04X}".format(crc & 0xFFFF)

def convert_qris_to_dynamic(qris, amount, service_fee=None, is_percent=False):
    qris = qris[:-4]
    qris = qris.replace("010211", "010212", 1)
    amount_str = f"54{len(str(amount)):02d}{amount}"
    qris_parts = re.split(r"5802ID", qris)
    final_qris = f"{qris_parts[0]}{amount_str}5802ID{qris_parts[1]}"
    final_qris += convert_crc16(final_qris)
    return final_qris

def string_to_qrcode_base64(data: str) -> str:
    qr = qrcode.make(data)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
