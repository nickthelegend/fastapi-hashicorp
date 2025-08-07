from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from algosdk import account, mnemonic
import requests
import os
from algosdk.transaction import AssetConfigTxn, AssetCreateTxn
from algosdk.v2client import algod
from dotenv import load_dotenv
import logging
import base64
import msgpack
from fastapi.encoders import jsonable_encoder

logging.basicConfig(
    level=logging.DEBUG,  # or logging.INFO to reduce verbosity
    format="%(asctime)s - %(levelname)s - %(message)s",
)
load_dotenv()  # Loads .env file into environment

class CreateRequest(BaseModel):
    key: str

class CreateAssetRequest(BaseModel):
    key: str
    asset_name: str
    unit_name: str
    total: int
    decimals: int
    default_frozen: bool = False
    url: str = None
    metadata_hash: str = None



app = FastAPI()

VAULT_ADDR = os.getenv("VAULT_ADDR", "https://hcv.goplausible.xyz")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
ALGOD_URL = os.getenv("ALGOD_URL")
ALGOD_TOKEN = ""


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



@app.post("/create-asset/")
def create_asset(req: CreateAssetRequest):
    # 1. Fetch mnemonic from cubbyhole
    vault_url = f"{VAULT_ADDR}/v1/cubbyhole/{req.key}"
    resp = requests.get(vault_url, headers={"X-Vault-Token": VAULT_TOKEN})
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Mnemonic not found in Vault.")
    logging.debug("Vault response status: %s, body: %s", resp.status_code, resp.text)

    mnem = resp.json()['data']['mnemonic']
    if not mnem:
        raise HTTPException(status_code=500, detail=f"Invalid mnemonic data.")

    # 2. Derive keys
    private_key = mnemonic.to_private_key(mnem)
    public_address = account.address_from_private_key(private_key)

    # 3. Initialize Algod client and get transaction params
    algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_URL)
    sp = algod_client.suggested_params()

    # 4. Build AssetConfigTxn
    txn = AssetConfigTxn(
        sender=public_address,
        sp=sp,
        total=req.total,
        default_frozen=req.default_frozen,
        unit_name=req.unit_name,
        asset_name=req.asset_name,
        manager=public_address,
        reserve=public_address,
        freeze=public_address,
        clawback=public_address,
        url=req.url,
        metadata_hash=req.metadata_hash.encode() if req.metadata_hash else None,
        decimals=req.decimals
    )

    # 5. Sign transaction
    signed_txn = txn.sign(private_key)
    data = {
        "sig": signed_txn.signature,                     # this is 'bytes'
        "txn": signed_txn.transaction.dictify()          # JSON-serializable
    }

    json_compatible = jsonable_encoder(data, custom_encoder={
        bytes: lambda v: base64.b64encode(v).decode("utf-8")
    })
    # 6. Return signed transaction
    return json_compatible
