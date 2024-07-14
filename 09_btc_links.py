from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import sqlite3
import time
from datetime import datetime, timezone
import os

DB_NAME = 'crypto_news.db'

def initialize_database():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
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

def scrape_and_store_links(driver):
    url = "https://finance.yahoo.com/topic/crypto/"
    driver.get(url)
    # driver.execute_script(f"document.body.style.zoom = '{0.1}'")
    wait = WebDriverWait(driver, 3)
    wait.until(EC.presence_of_element_located((By.ID, "Fin-Stream")))

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    fin_stream = soup.find('div', id='Fin-Stream')
    if fin_stream:
        links = [a['href'] for a in fin_stream.find_all('a', href=True)]
    else:
        print("Fin-Stream div not found")
        return

    now = datetime.now(timezone.utc)
    now_unix = int(now.timestamp())
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    for link in links:
        if ("/news/" in link) and (".html" in link) and ("https:" in link):
            cur.execute("""
                INSERT OR IGNORE INTO links (url, first_seen_utc, first_seen_unix)
                VALUES (?, ?, ?)
            """, (link, now, now_unix))
            if cur.rowcount > 0:
                print("Added new link:", link)
    
    conn.commit()
    conn.close()
    
    print(f"Link scraping completed at {now}")

def main():
    initialize_database()

    print("Initializing Firefox driver")
    options = Options()
    # options.add_argument('-headless')
    options.set_preference('permissions.default.image', 2)
    service = Service('geckodriver')  # Replace with the path to your geckodriver
    driver = webdriver.Firefox(service=service, options=options)
    print("Initialize completed")

    try:
        while True:
            try:
                scrape_and_store_links(driver)
            except Exception as e:
                print(f"Error occurred: {e}")
    except KeyboardInterrupt:
        print("Link scraper manually terminated.")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()