import requests

try:
    print("Getting invoice...")
    response = requests.post("http://localhost:8000/api/services/77441d03-c2b3-480f-ac75-548e29ff1136/call", json={"input": "test"})
    print(response.status_code)
    print(response.headers)
    
    if response.status_code == 402:
        www_auth = response.headers.get("WWW-Authenticate", "")
        import re
        macaroon = re.search(r'macaroon="([^"]+)"', www_auth).group(1)
        invoice = re.search(r'invoice="([^"]+)"', www_auth).group(1)
        
        print("Mock paying invoice...")
        # Since the consumer script successfully called pay_invoice, we will too
        import json
        ph = invoice.split("mock")[-1]
        with open("mock_payments.json", "r+") as f:
            data = json.load(f)
            if ph in data:
                data[ph] = "settled"
            f.seek(0)
            json.dump(data, f)
            f.truncate()
            
        print("Re-calling with auth...")
        headers = {"Authorization": f"L402 {macaroon}:000000"}
        res2 = requests.post("http://localhost:8000/api/services/77441d03-c2b3-480f-ac75-548e29ff1136/call", json={"input": "test"}, headers=headers)
        with open("error.log", "w") as f:
            f.write(res2.text)

except Exception as e:
    print("Error:", e)
