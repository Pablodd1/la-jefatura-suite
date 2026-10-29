"""
La Jefatura Suite — Register Juan's Phone Number on Meta WhatsApp Cloud API
Automates:
  1. POST /{waba_id}/phone_numbers (adds +1 786 657 5441 to WABA)
  2. POST /{new_phone_id}/request_code (sends SMS/voice code to Juan's phone)
  3. POST /{new_phone_id}/verify_code (verifies the 6-digit code)
  4. POST /{new_phone_id}/register (registers with Cloud API PIN)
  5. Updates data/meta_whatsapp.secret.json with the new phone_number_id
"""

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = r"C:\Users\jasme\la-jefatura-suite"
SECRET_FILE = os.path.join(ROOT, "data", "meta_whatsapp.secret.json")

def api_call(path, token, method="GET", payload=None):
    url = f"https://graph.facebook.com/v21.0/{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "LaJefatura-MetaCloudAPI/1.0"
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        return {"http_error": e.code, "body": body}
    except Exception as e:
        return {"error": str(e)}

def add_phone_number(token, waba_id, phone="7866575441", cc="1", verified_name="Unitec USA - Juan"):
    payload = {
        "cc": cc,
        "phone_number": phone,
        "verified_name": verified_name
    }
    return api_call(f"{waba_id}/phone_numbers", token, method="POST", payload=payload)

def request_sms_code(token, phone_number_id, method="SMS", lang="es"):
    payload = {
        "code_method": method,
        "language": lang
    }
    return api_call(f"{phone_number_id}/request_code", token, method="POST", payload=payload)

def verify_code(token, phone_number_id, code):
    payload = {
        "code": code
    }
    return api_call(f"{phone_number_id}/verify_code", token, method="POST", payload=payload)

def register_phone(token, phone_number_id, pin="123456"):
    payload = {
        "messaging_product": "whatsapp",
        "pin": pin
    }
    return api_call(f"{phone_number_id}/register", token, method="POST", payload=payload)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python register_juan_phone.py <ACCESS_TOKEN> [WABA_ID] [VERIFY_CODE]")
        sys.exit(1)
    
    token = sys.argv[1]
    cfg = json.load(open(SECRET_FILE, encoding="utf-8")) if os.path.isfile(SECRET_FILE) else {}
    waba_id = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "default" else (cfg.get("waba_id") or "1454434806634014")
    
    print(f"Connecting to Meta WABA: {waba_id}...")
    
    # Check if a 6-digit code was provided to complete verification
    if len(sys.argv) > 3:
        phone_id = cfg.get("pending_phone_id")
        code = sys.argv[3]
        print(f"Verifying code {code} for Phone ID {phone_id}...")
        res = verify_code(token, phone_id, code)
        print("Verify response:", json.dumps(res, indent=2))
        if res.get("success"):
            reg_res = register_phone(token, phone_id)
            print("Register response:", json.dumps(reg_res, indent=2))
            cfg["phone_number_id"] = phone_id
            cfg["juan_phone_number"] = "+17866575441"
            cfg["access_token"] = token
            with open(SECRET_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            print(f"SUCCESS! Juan's phone {cfg['juan_phone_number']} is now live with Phone ID {phone_id}!")
        sys.exit(0)

    # Step 1: Add phone number to WABA
    res = add_phone_number(token, waba_id, phone="7866575441", cc="1", verified_name="Unitec USA - Juan")
    print("Add phone response:", json.dumps(res, indent=2))
    
    new_phone_id = res.get("id")
    if not new_phone_id and "body" in res:
        # Check if already added or error details
        try:
            err_data = json.loads(res["body"])
            print("Meta Error Message:", err_data.get("error", {}).get("message"))
        except Exception:
            pass
    elif new_phone_id:
        cfg["pending_phone_id"] = new_phone_id
        cfg["access_token"] = token
        with open(SECRET_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        print(f"\nCreated Phone ID: {new_phone_id}")
        print("Requesting SMS verification code to +1 (786) 657-5441...")
        sms_res = request_sms_code(token, new_phone_id, method="SMS", lang="es")
        print("SMS request response:", json.dumps(sms_res, indent=2))
        print(f"\nPlease check Juan's phone (+1 786 657 5441) for the 6-digit Meta code.")
