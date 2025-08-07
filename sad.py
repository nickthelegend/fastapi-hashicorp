from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from algosdk import account, mnemonic
import requests
import os

class CreateRequest(BaseModel):
    key: str

app = FastAPI()

VAULT_ADDR = os.getenv("VAULT_ADDR", "https://hcv.goplausible.xyz")
VAULT_TOKEN = "hvs.CAESILy7TZ5io0-A2goc9nFpq8eT1hTWtj6tBRh2J1s4-VYvGh4KHGh2cy5qbHRwZHhiRXJkclFlZ25OaXVrR1FmREI"

@app.post("/create/")
def create_wallet(req: CreateRequest):
    path = req.key
    url = f"{VAULT_ADDR}/v1/cubbyhole/{path}"
    headers = {
        "X-Vault-Token": VAULT_TOKEN,
    }

    # 1. Check if mnemonic already exists
    check_resp = requests.get(url, headers=headers)
    if check_resp.status_code == 200:
        try:
            data = check_resp.json()
            mnem = data['data']['mnemonic']
            address = account.address_from_private_key(mnemonic.to_private_key(mnem))
            return {
                "key": path,
                "address": address,
                "status": "existing"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail="Vault response error or corrupted mnemonic.")

    # 2. Create new account if not exists
    private_key, address = account.generate_account()
    mnem = mnemonic.from_private_key(private_key)

    # 3. Store new mnemonic in cubbyhole
    vault_payload = {"mnemonic": mnem}
    store_resp = requests.post(url, json=vault_payload, headers={**headers, "Content-Type": "application/json"})

    if store_resp.status_code not in [200, 204]:
        raise HTTPException(status_code=500, detail="Failed to store mnemonic in Vault.")

    return {
        "key": path,
        "address": address,
        "status": "created"
    }
