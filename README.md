### Create wallet 
```bash
curl -X POST "http://127.0.0.1:8000/create/" -H "Content-Type: application/json" -d "{\"key\": \"sad\"}"
```


### Create Asset /create-asset/


```bash
curl -X POST "http://127.0.0.1:8000/create-asset/" -H "Content-Type: application/json" -d "{\"key\":\"sad\",\"asset_name\":\"MyToken\",\"unit_name\":\"MTK\",\"total\":1000,\"decimals\":0}"

```