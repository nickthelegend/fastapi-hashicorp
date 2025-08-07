### Create wallet 
```bash
curl -X POST "http://127.0.0.1:8000/create/" -H "Content-Type: application/json" -d "{\"key\": \"sad\"}"
```


### Create Asset /create-asset/


```bash
curl -X POST "http://127.0.0.1:8000/create-asset/" -H "Content-Type: application/json" -d "{\"key\":\"sad\",\"asset_name\":\"MyToken\",\"unit_name\":\"MTK\",\"total\":1000,\"decimals\":0}"

```



### Payment Txn /payment
```bash
curl -X POST "http://127.0.0.1:8000/create-asset/" -H "Content-Type: application/json" -d "{\"key\":\"sad\",\"asset_name\":\"MyToken\",\"unit_name\":\"MTK\",\"total\":1000,\"decimals\":0}"
```

### Asset Transfer /asset-transfer

```bash
curl -X POST http://127.0.0.1:8000/payment/ -H "Content-Type: application/json" -d "{\"key\":\"sad\",\"receiver\":\"LEGENDMQQJJWSQVHRFK36EP7GTM3MTI3VD3GN25YMKJ6MEBR35J4SBNVD4\",\"amount\":1000}"
```

### Asset Opt-IN /opt-in-asset/
```bash
curl -X POST http://127.0.0.1:8000/opt-in-asset/ -H "Content-Type: application/json" -d "{\"key\":\"sad\",\"asset_id\":1234}"
```

### Asset Opt-OUT /asset-opt-out/
```bash
curl -X POST http://127.0.0.1:8000/asset-opt-out/ -H "Content-Type: application/json" -d "{\"key\":\"sad\",\"asset_id\":1234,\"receiver\":\"LEGENDMQQJJWSQVHRFK36EP7GTM3MTI3VD3GN25YMKJ6MEBR35J4SBNVD4\"}"
```