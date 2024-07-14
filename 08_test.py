import requests
import json
import datetime
import time

# Server-URL
SERVER_URL = 'http://localhost:5556'

# Add template
add_template_url = f'{SERVER_URL}/add_template'
template_data = {
    'name': 'yahoo_finance',
    'template': {
        'title': 'h1[data-test-locator="headline"]',
        'author': 'span.caas-author-byline-collapse',
        'date': {'selector': 'time', 'attribute': 'datetime','index':[0]},
        'article': 'div.caas-body',
        'ticker_symbols': {'selector': 'div.caas-body-content', 'attribute': 'data-symbol', 'index':[0], 'inner':{'selector': 'fin-ticker', 'attribute': 'symbol'}},
    }
}

response = requests.post(add_template_url, json=template_data)
print("Template added:", response.text)

# List of URLs to test
urls_to_test = [
    'https://finance.yahoo.com/news/bitcoin-drops-anew-fears-sales-041755427.html',
    'https://finance.yahoo.com/news/top-3-crypto-investments-buy-083200729.html',
    'https://finance.yahoo.com/news/crypto-thieves-stolen-1-38-064540816.html',
    'https://finance.yahoo.com/news/bitcoin-spot-etfs-saw-143m-062619490.html',
    'https://finance.yahoo.com/news/bitcoin-drops-below-55-000-061818898.html',
    'https://finance.yahoo.com/news/bitcoins-bullish-indicators-emerge-despite-061524009.html',
    'https://finance.yahoo.com/news/germany-sill-holds-2-2b-055818481.html',
    'https://finance.yahoo.com/news/coindesk-20-down-7-bitcoin-042755541.html',
    'https://finance.yahoo.com/news/bitcoin-bulls-eye-100-000-190000484.html'
]

def convert_utc_to_unix(utc_time):
    dt = datetime.datetime.strptime(utc_time, "%Y-%m-%dT%H:%M:%S.%fZ")
    unix_timestamp = int(dt.timestamp())
    return unix_timestamp

# Extract and get article for each URL
extract_and_get_url = f'{SERVER_URL}/extract_and_get_article'

# Submit all requests
request_ids = []
for url in urls_to_test:
    article_data = {
        'url': url,
        'template': 'yahoo_finance'
    }
    response = requests.post(extract_and_get_url, json=article_data)
    if response.status_code == 200:
        request_id = response.json().get('request_id')
        if request_id:
            request_ids.append((url, request_id))
            print(f"Submitted request for {url}, request ID: {request_id}")
        else:
            print(f"Failed to get request ID for {url}")
    else:
        print(f"Failed to submit request for {url}: {response.text}")

# Wait for a bit to allow processing
print("Waiting for 10 seconds to allow processing...")
time.sleep(10)

# Check results
get_result_url = f'{SERVER_URL}/get_result'
for url, request_id in request_ids:
    print(f"\nChecking result for {url}")
    response = requests.get(f"{get_result_url}/{request_id}")
    
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2))

        # Checks
        assert 'title' in result, "Title not found in extracted data"
        assert 'author' in result, "Author not found in extracted data"
        assert 'date' in result, "Date not found in extracted data"
        assert 'article' in result, "Article content not found in extracted data"
        
        # Optional: Check for ticker_symbols
        if 'ticker_symbols' in result:
            print("Ticker symbols found:", result['ticker_symbols'])

        print("All checks passed for this URL.")
    else:
        print(f"Error getting result: {response.text}")

print("\nAll tests completed.")