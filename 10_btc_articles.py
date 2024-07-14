import json
from dateutil import parser
import time
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from urllib3.exceptions import ProtocolError
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import multiprocessing
import queue
import time
import random
import logging
import sqlite3

# Set up logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# Database configuration
DB_NAME = 'crypto_news.db'

# Template data
template_data = {
    'name': 'yahoo_finance',
    'template': {
        'title': 'h1[data-test-locator="headline"]',
        'author': 'span.caas-author-byline-collapse',
        'datetime': {'selector': 'time', 'attribute': 'datetime', 'index': [0]},
        'article': 'div.caas-body',
        'ticker_symbols': {'selector': 'div.caas-body-content', 'attribute': 'data-symbol', 'index': [0], 'inner': {'selector': 'fin-ticker', 'attribute': 'symbol'}},
        'source': 'a[class="link caas-attr-provider-logo"]',
        'sourcr_url': {'selector': 'a[class="link caas-attr-provider-logo"]', 'attribute': 'href', 'index': [0]},
    }
}

# Global variables
templates = {template_data['name']: template_data['template']}
manager = multiprocessing.Manager()
results = manager.dict()
url_queue = multiprocessing.Queue()
NUM_BROWSERS = 5

def initialize_database():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            url TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            datetime_utc TIMESTAMP,
            datetime_unix INTEGER,
            content TEXT,
            ticker_symbols TEXT,
            FOREIGN KEY (url) REFERENCES links (url)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            url TEXT PRIMARY KEY,
            first_seen_utc TIMESTAMP,
            first_seen_unix INTEGER,
            is_scraped INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_unscraped_links():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT url FROM links WHERE is_scraped = 0")
    links = [row[0] for row in cur.fetchall()]
    conn.close()
    return links

def store_article(url, article_data):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Convert all values to strings or None
    title = str(article_data.get('title')) if article_data.get('title') is not None else None
    author = str(article_data.get('author')) if article_data.get('author') is not None else None
    datetime = str(article_data.get('datetime')[0]) if article_data.get('datetime') is not None else None
    content = str(article_data.get('article')) if article_data.get('article') is not None else None
    ticker_symbols = json.dumps(article_data.get('ticker_symbols')) if article_data.get('ticker_symbols') is not None else None
    
    # print(datetime)
    # Convert date to UTC and UNIX timestamps
    datetime_utc = None
    datetime_unix = None
    if datetime:
        try:
            parsed_date = parser.parse(datetime)
            datetime_utc = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
            datetime_unix = int(time.mktime(parsed_date.timetuple()))
        except ValueError:
            logging.warning(f"Invalid date format for URL {url}: {datetime}")    
    
    cur.execute("""
        INSERT OR REPLACE INTO articles (url, title, author, content, datetime_utc, datetime_unix, ticker_symbols)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (url, title, author, content, datetime_utc, datetime_unix, ticker_symbols))
    
    cur.execute("UPDATE links SET is_scraped = 1 WHERE url = ?", (url,))
    
    conn.commit()
    conn.close()

def initialize_browser(worker_id):
    options = Options()
    # options.add_argument('-headless')
    options.set_preference('permissions.default.image', 2)
    options.set_preference('javascript.enabled', False)
    options.set_preference('media.autoplay.default', 5)
    options.set_preference('media.volume_scale', '0.0')

    service = Service('geckodriver')  # Replace with the path to your geckodriver

    logging.debug(f"Initializing browser for worker {worker_id}")

    for attempt in range(3):
        try:
            logging.debug(f"Attempt {attempt + 1} to initialize browser for worker {worker_id}")
            driver = webdriver.Firefox(service=service, options=options)
            logging.debug(f"Browser successfully initialized for worker {worker_id}")
            return driver
        except Exception as e:
            logging.error(f"Error initializing browser for worker {worker_id} (attempt {attempt + 1}): {e}")
            time.sleep(random.uniform(1, 3))

    raise Exception(f"Failed to initialize browser for worker {worker_id} after 3 attempts")

def extract_article_data(driver, url, template_name):
    try:
        driver.get(url)
        driver.execute_script(f"document.body.style.zoom = '{0.1}'")
        wait = WebDriverWait(driver, 3)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
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
                        elements = [elements[i] for i in index if i < len(elements)]
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

def worker(worker_id):
    logging.info(f"Worker {worker_id} starting")
    time.sleep(worker_id * 0.5)
    try:
        driver = initialize_browser(worker_id)
        logging.info(f"Worker {worker_id} initialized")
        
        while True:
            try:
                url = url_queue.get(timeout=5)
                if url not in results:
                    logging.debug(f"Worker {worker_id} processing {url}")
                    article_data = extract_article_data(driver, url, 'yahoo_finance')
                    if article_data:
                        results[url] = article_data
                        store_article(url, article_data)
                        logging.info(f"Worker {worker_id} processed and stored {url}")
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

def start_workers():
    processes = []
    for i in range(NUM_BROWSERS):
        p = multiprocessing.Process(target=worker, args=(i,))
        p.start()
        processes.append(p)
    return processes

def main():
    initialize_database()
    worker_processes = start_workers()

    try:
        while True:
            unscraped_links = get_unscraped_links()
            
            if not unscraped_links:
                continue

            for link in unscraped_links:
                url_queue.put(link)
                time.sleep(0.1)  # Small delay to prevent overwhelming the queue

    except KeyboardInterrupt:
        print("Scraper manually terminated.")
    finally:
        # Wait for all worker processes to finish
        for p in worker_processes:
            p.join()

if __name__ == "__main__":
    main()