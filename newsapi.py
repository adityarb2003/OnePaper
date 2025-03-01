import requests

api_key = ''
url = 'https://newsapi.org/v2/sources'

params = {
    'apiKey': api_key,
}

response = requests.get(url, params=params)

if response.status_code == 200:
    sources_data = response.json()

    for source in sources_data['sources']:
        print(f"Name: {source['name']}, ID: {source['id']}")
else:
    print(f"Error fetching sources: {response.status_code}")
