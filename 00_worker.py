import json
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import multiprocessing
import queue
import threading
import time

app = Flask(__name__)

# Vorlagenspeicher
templates = {}
# Browser-Instanz
driver = None
# Ergebnisspeicher
results = {}

def load_templates():
    global templates
    try:
        with open('templates.json', 'r') as file:
            templates = json.load(file)
    except FileNotFoundError:
        templates = {}

def initialize_browser():
    global driver
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)

def extract_article_data(url, template_name):
    global driver
    
    driver.get(url)

    try:
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

        template = templates.get(template_name)
        if template:
            article_data = {}
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            for field, selector in template.items():
                try:
                    element = soup.select_one(selector)
                    if element:
                        article_data[field] = element.get_text(strip=True)
                    else:
                        article_data[field] = ''
                except:
                    article_data[field] = ''
            
            # Füge den ursprünglichen HTML-Quelltext hinzu
            article_data['html_source'] = page_source
            
            return article_data
        else:
            print(f"Template '{template_name}' not found.")
            return None
    except TimeoutException:
        print("Page load timeout. Skipping extraction.")
        return None

def save_result_to_storage(url, article_data):
    results[url] = article_data

@app.route('/process_and_get_task', methods=['POST'])
def process_and_get_task():
    task = request.get_json()
    url = task['url']
    template_name = task['template']

    # Überprüfen, ob das Ergebnis bereits im Speicher ist
    if url in results:
        return jsonify(results[url])

    # Wenn nicht, extrahieren wir die Daten
    article_data = extract_article_data(url, template_name)
    if article_data:
        save_result_to_storage(url, article_data)
        return jsonify(article_data)
    else:
        return jsonify({'message': 'Failed to extract data', 'url': url}), 400

if __name__ == '__main__':
    load_templates()
    initialize_browser()
    app.run(port=5001)  # Run on a different port than the server