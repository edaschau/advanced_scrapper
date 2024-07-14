import json
import undetected_chromedriver as uc
from urllib3.exceptions import ProtocolError
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import multiprocessing
import queue
import time
import os
import random
import logging

# Set up logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Vorlagenspeicher
templates = {}
# Ergebnisspeicher (als Manager-Dict für Multiprocessing)
manager = multiprocessing.Manager()
results = manager.dict()
# Warteschlange für URLs
url_queue = multiprocessing.Queue()
# Anzahl der Browser-Instanzen
NUM_BROWSERS = 5



def load_templates():
    global templates
    try:
        with open('templates.json', 'r') as file:
            templates = json.load(file)
        logging.debug(f"Templates loaded: {templates}")
    except FileNotFoundError:
        logging.warning("templates.json not found. Using empty templates.")
        templates = {}

def initialize_browser(worker_id, port):
    options = uc.ChromeOptions()
    options.add_argument(f'--user-data-dir=/tmp/chrome_profile_{worker_id}')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument('--disable-javascript')
    options.add_argument('--autoplay-policy=user-gesture-required')
    options.add_argument('--disable-features=AutoplayIgnoreWebAudio')
    options.add_argument('--disable-audio-output')
    options.add_argument('--mute-audio')
    options.add_argument('--enable-distillation')

    logging.debug(f"Initializing browser for worker {worker_id}")
    logging.info(f"Worker {worker_id} using port {port}")

    for attempt in range(3):
        try:
            logging.debug(f"Attempt {attempt + 1} to initialize browser for worker {worker_id}")
            driver = uc.Chrome(options=options, port=port)
            logging.debug(f"Browser successfully initialized for worker {worker_id} on port {port}")
            return driver
        except Exception as e:
            logging.error(f"Error initializing browser for worker {worker_id} on port {port} (attempt {attempt + 1}): {e}")
            time.sleep(random.uniform(1, 3))

    raise Exception(f"Failed to initialize browser for worker {worker_id} after 3 attempts")

def extract_article_data(driver, url, template_name):
    try:
        driver.get(url)
        # ... rest of your extraction logic ...
    except ProtocolError as e:
        logging.error(f"Protocol error for {url}: {e}")
        # Analyze the exception details
        if "Connection aborted" in str(e):
            logging.error("Connection was aborted. Possible network instability.")
        elif "Connection refused" in str(e):
            logging.error("Connection was refused. Possible firewall or server issue.")
        # Add more specific error checks as needed
    except WebDriverException as e:
        logging.error(f"WebDriver exception for {url}: {e}")
        # Analyze WebDriver-specific issues
    except Exception as e:
        logging.error(f"Unexpected error for {url}: {e}")

    # Add network request logging
    logs = driver.get_log('performance')
    for entry in logs:
        logging.debug(f"Network log: {entry}")
    try:
        wait = WebDriverWait(driver, 5)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        print(f"\nBody element found for URL: {url}\n\n")
        logging.debug(f"Body element found for URL: {url}")

        template = templates.get(template_name)
        if template:
            article_data = {}
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            def extract_elements(selector_info, parent_element):
                selector = selector_info['selector']
                attribute = selector_info['attribute']
                index = selector_info.get('index')
                inner = selector_info.get('inner', [])

                elements = parent_element.select(selector)
                if elements:
                    if index:
                        # If index is provided, use it
                        elements = [elements[i] for i in index if i < len(elements)]
                    # If no index is provided, or if it's an empty list, use all elements
                    value = []
                    for element in elements:              
                        if inner:
                            inner_value = []
                            inner_value.extend(extract_elements(inner, element))
                            value.append(inner_value)
                        else:
                            if attribute == 'text':
                                value.append(element.get_text(strip=True))
                            else:
                                value.append(element.get(attribute))
                    return value
                else:
                    logging.debug(f"No elements found for selector: {selector}")
                    return []
                
            for field, selector_info in template.items():
                try:
                    if isinstance(selector_info, dict):
                        value = extract_elements(selector_info, soup)
                        article_data[field] = value
                    else:
                        element = soup.select_one(selector_info)
                        if element:
                            article_data[field] = element.get_text(strip=True)
                        else:
                            article_data[field] = ''

                    logging.debug(f"Extracted {field}: {article_data[field][:50]}...")
                except Exception as e:
                    logging.error(f"Error extracting {field}: {e}")
                    article_data[field] = ''

            article_data['html_source'] = page_source
            logging.debug(f"Extraction completed for URL: {url}")
            return article_data
        else:
            logging.warning(f"Template '{template_name}' not found.")
            return None
    except TimeoutException:
        logging.warning(f"Page load timeout for URL: {url}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error during extraction for URL {url}: {e}")
        return None

def worker(worker_id, port):
    logging.info(f"Worker {worker_id} starting")
    time.sleep(worker_id * 0.5)
    try:
        driver = initialize_browser(worker_id, port)
        logging.info(f"Worker {worker_id} initialized on port {port}")
        
        while True:
            try:
                task = url_queue.get(timeout=5)
                url = task['url']
                template_name = task['template']
                
                if url not in results:
                    logging.debug(f"Worker {worker_id} processing {url}")
                    article_data = extract_article_data(driver, url, template_name)
                    if article_data:
                        results[url] = article_data
                        logging.info(f"Worker {worker_id} processed {url}")
                    else:
                        logging.warning(f"Worker {worker_id} failed to extract data from {url}")
                else:
                    logging.debug(f"Worker {worker_id} skipped {url} (already processed)")
            except queue.Empty:
                logging.debug(f"Worker {worker_id} empty queue")
            except Exception as e:
                logging.error(f"Error in worker {worker_id}: {e}")
                
    except Exception as e:
        logging.critical(f"Critical error in worker {worker_id}: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
        logging.info(f"Worker {worker_id} finished")

@app.route('/process_and_get_task', methods=['POST'])
def process_and_get_task():
    logging.info("Processing and getting task")
    task = request.get_json()
    url = task['url']
    template_name = task['template']

    if url in results:
        logging.info(f"Result for {url} already in cache, returning immediately")
        return jsonify(results[url])

    logging.info(f"Adding task for {url} to queue")
    url_queue.put(task)

    timeout = 5
    start_time = time.time()
    while url not in results:
        # print(results)
        time.sleep(0.1)
        if time.time() - start_time > timeout:
            logging.warning(f"Processing {timeout} timeout for {url}")
            return jsonify({'message': 'Processing timeout', 'url': url}), 408
    
    logging.info(f"Returning result for {url}")
    return jsonify(results[url])

def start_workers():
    processes = []
    start_port = 9000
    for i in range(NUM_BROWSERS):
        p = multiprocessing.Process(target=worker, args=(i, start_port + i))
        p.start()
        processes.append(p)
    return processes

if __name__ == '__main__':
    load_templates()
    worker_processes = start_workers()
    app.run(port=5555)
    
    # Warten auf das Beenden aller Worker-Prozesse
    for p in worker_processes:
        p.join()