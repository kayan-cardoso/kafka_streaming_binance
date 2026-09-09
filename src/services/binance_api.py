import requests 

def get_precos() -> list:
    url_principal = "https://api.binance.com/api/v3/ticker/price" # URL onde pegamos os preços 
    url2 = 'https://api.binance.com/api/v3/ticker/24hr'


    volume = requests.get(url2).json()

    top_50 = sorted([
        x for x in volume 
        if x['symbol'].endswith('USDT')
        ], 
        key=lambda x:float(x['quoteVolume']),
        reverse=True)[0:50]

    symbols = [x['symbol'] for x in top_50]

    price = requests.get(url_principal).json()

    list_50 = []
    for item in price:
        if item['symbol'] in symbols:
            list_50.append(item)

    return list_50

if __name__ == '__main__':
    get_precos()



