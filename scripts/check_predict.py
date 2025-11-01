import urllib.request, json, time, sys
url='http://127.0.0.1:8000/predict/'
for i in range(8):
    try:
        r=urllib.request.urlopen(url, timeout=5)
        txt=r.read().decode('utf-8')
        data=json.loads(txt)
        print('OK keys=', list(data.keys()))
        sys.exit(0)
    except Exception as e:
        print('Attempt',i,'error:',e)
        time.sleep(1)
print('FAILED to reach', url)
sys.exit(1)
