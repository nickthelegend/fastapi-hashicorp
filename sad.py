from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from algosdk import account, mnemonic
import requests
import os
from algosdk.transaction import AssetConfigTxn, AssetCreateTxn , PaymentTxn , AssetTransferTxn , AssetOptInTxn, AssetCloseOutTxn
from algosdk.v2client import algod
from dotenv import load_dotenv
import logging
import base64
import msgpack
from fastapi.encoders import jsonable_encoder
from algosdk.v2client.algod import AlgodClient

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

class PaymentRequest(BaseModel):
    key: str
    receiver: str
    amount: int

class AssetTransferRequest(BaseModel):
    key: str
    receiver: str
    asset_id: int
    amount: int
    close_to: str | None = None
    revocation_target: str | None = None

class OptInRequest(BaseModel):
    key: str
    asset_id: int

class AssetOptOutRequest(BaseModel):
    key: str
    asset_id: int
    receiver: str  # recipient of remaining assets (usually reserve or clawback)
    note: bytes | None = None

app = FastAPI()

VAULT_ADDR = os.getenv("VAULT_ADDR", "https://hcv.goplausible.xyz")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
ALGOD_URL = os.getenv("ALGOD_URL")
ALGOD_TOKEN = ""
algod_client = AlgodClient(ALGOD_TOKEN, ALGOD_URL)


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

@app.post("/payment/")
def payment_txn(req: PaymentRequest):
    # 1. Retrieve mnemonic securely from Vault's cubbyhole using the user-provided key
    vault_url = f"{VAULT_ADDR}/v1/cubbyhole/{req.key}"
    resp = requests.get(vault_url, headers={"X-Vault-Token": VAULT_TOKEN})
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Mnemonic not found in Vault.")
    mnem = resp.json().get("data", {}).get("mnemonic")
    if not mnem:
        raise HTTPException(status_code=500, detail="Invalid mnemonic data.")

    # 2. Derive Algorand keys
    private_key = mnemonic.to_private_key(mnem)
    sender_addr = account.address_from_private_key(private_key)

    # 3. Build a payment transaction
    sp = algod_client.suggested_params()
    txn = PaymentTxn(sender=sender_addr, sp=sp, receiver=req.receiver, amt=req.amount)

    # 4. Sign the transaction
    signed_txn = txn.sign(private_key)

    # 5. Construct response dict with safe serialization
    data = {
        "sig": signed_txn.signature,                 # raw bytes
        "txn": signed_txn.transaction.dictify()     # JSON-ready dict
    }
    return jsonable_encoder(data, custom_encoder={bytes: lambda v: base64.b64encode(v).decode("utf-8")})

@app.post("/asset-transfer/")
def asset_transfer(req: AssetTransferRequest):
    # 1. Retrieve mnemonic from Vault
    vault_url = f"{VAULT_ADDR}/v1/cubbyhole/{req.key}"
    resp = requests.get(vault_url, headers={"X-Vault-Token": VAULT_TOKEN})
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Mnemonic not found in Vault.")
    mnem = resp.json().get("data", {}).get("mnemonic")
    if not mnem:
        raise HTTPException(status_code=500, detail="Invalid mnemonic data.")

    # 2. Derive keys
    private_key = mnemonic.to_private_key(mnem)
    sender_addr = account.address_from_private_key(private_key)

    # 3. Build AssetTransferTxn
    sp = algod_client.suggested_params()
    txn = AssetTransferTxn(
        sender=sender_addr,
        sp=sp,
        receiver=req.receiver,
        amt=req.amount,
        index=req.asset_id,
        close_assets_to=req.close_to,
        revocation_target=req.revocation_target
    )

    # 4. Sign transaction
    signed_txn = txn.sign(private_key)

    # 5. Prepare JSON response handling bytes
    data = {
        "sig": signed_txn.signature,
        "txn": signed_txn.transaction.dictify()
    }
    return jsonable_encoder(data, custom_encoder={bytes: lambda v: base64.b64encode(v).decode("utf-8")})

@app.post("/opt-in-asset/")
def opt_in_asset(req: OptInRequest):
    # 1. Fetch mnemonic from Vault
    vault_url = f"{VAULT_ADDR}/v1/cubbyhole/{req.key}"
    resp = requests.get(vault_url, headers={"X-Vault-Token": VAULT_TOKEN})
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Mnemonic not found in Vault.")
    mnem = resp.json().get("data", {}).get("mnemonic")
    if not mnem:
        raise HTTPException(status_code=500, detail="Invalid mnemonic data.")

    # 2. Derive Algorand account
    private_key = mnemonic.to_private_key(mnem)
    sender_addr = account.address_from_private_key(private_key)

    # 3. Build AssetOptInTxn (opt-in = asset opt-in)
    sp = algod_client.suggested_params()
    txn = AssetOptInTxn(sender=sender_addr, sp=sp, index=req.asset_id)

    # 4. Sign transaction
    signed_txn = txn.sign(private_key)

    # 5. Construct safe JSON response
    data = {
        "sig": signed_txn.signature,                   # raw bytes
        "txn": signed_txn.transaction.dictify()        # JSON-ready dict
    }
    return jsonable_encoder(data, custom_encoder={
        bytes: lambda v: base64.b64encode(v).decode("utf-8")
    })

@app.post("/asset-opt-out/")
def asset_opt_out(req: AssetOptOutRequest):
    # 1. Fetch mnemonic from Vault
    vault_url = f"{VAULT_ADDR}/v1/cubbyhole/{req.key}"
    resp = requests.get(vault_url, headers={"X-Vault-Token": VAULT_TOKEN})
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Mnemonic not found in Vault.")
    mnem = resp.json().get("data", {}).get("mnemonic")
    if not mnem:
        raise HTTPException(status_code=500, detail="Invalid mnemonic data.")

    # 2. Derive Algorand keys
    private_key = mnemonic.to_private_key(mnem)
    sender_addr = account.address_from_private_key(private_key)

    # 3. Build AssetCloseOutTxn
    sp = algod_client.suggested_params()
    txn = AssetCloseOutTxn(
        sender=sender_addr,
        sp=sp,
        receiver=req.receiver,
        index=req.asset_id,
        note=req.note
    )

    # 4. Sign transaction
    signed_txn = txn.sign(private_key)

    # 5. Return safe JSON response with Base64 for bytes
    data = {
        "sig": signed_txn.signature,
        "txn": signed_txn.transaction.dictify()
    }
    return jsonable_encoder(data, custom_encoder={
        bytes: lambda v: base64.b64encode(v).decode("utf-8")
    })