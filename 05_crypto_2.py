#Get the real time crypto news from yahoo finance.

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import time
from datetime import datetime, timezone
import pandas as pd
import os
import requests
import json

# Server URL for the scraper
SERVER_URL = 'http://localhost:5556'

def create_database_if_not_exists(dbname, user, password, host):
    conn = psycopg2.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (dbname,))
    exists = cur.fetchone()
    
    if not exists:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        print(f"Database {dbname} created.")
    else:
        print(f"Database {dbname} already exists.")

    cur.close()
    conn.close()

def initialize_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS crypto_links (
            url TEXT PRIMARY KEY,
            first_seen_utc TIMESTAMP,
            first_seen_unix BIGINT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS crypto_articles (
            url TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            date TEXT,
            article TEXT,
            ticker_symbols TEXT
        )
    """)
    conn.commit()
    cur.close()

def scrape_and_store(conn, driver, csv_file):
    url = "https://finance.yahoo.com/topic/crypto/"
    driver.get(url)
    
    wait = WebDriverWait(driver, 3)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href]")))

    scroll_pause_time = 1
    scroll_attempts = 3
    
    for _ in range(scroll_attempts):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    links = [a['href'] for a in soup.find_all('a', href=True)]
    now = datetime.now()
    now_utc = datetime.now(timezone.utc)
    now_unix = int(now.timestamp())
    
    cur = conn.cursor()
    new_data = []
    
    for link in links:
        if ("/news/" in link) and (".html" in link) and ("https:" in link):
            cur.execute("""
                INSERT INTO crypto_links (url, first_seen_utc, first_seen_unix)
                VALUES (%s, %s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (link, now_utc, now_unix))

            if cur.rowcount > 0:
                print("ADD:", link)
                new_data.append([link, now_utc, now_unix])
                scrape_article(conn, link)
    
    conn.commit()
    cur.close()
    
    if new_data:
        if os.path.isfile(csv_file):
            existing_data = pd.read_csv(csv_file)
            new_df = pd.DataFrame(new_data, columns=['url', 'first_seen_utc', 'first_seen_unix'])
            combined_data = pd.concat([existing_data, new_df], ignore_index=True)
            combined_data.to_csv(csv_file, index=False)
        else:
            df = pd.DataFrame(new_data, columns=['url', 'first_seen_utc', 'first_seen_unix'])
            df.to_csv(csv_file, index=False)
    
    print(f"Scraping completed at {now}")

def scrape_article(conn, url):
    extract_and_get_url = f'{SERVER_URL}/extract_and_get_article'
    article_data = {
        'url': url,
        'template': 'yahoo_finance'
    }
    response = requests.post(extract_and_get_url, json=article_data)

    if response.status_code == 200:
        result = response.json()
        
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO crypto_articles (url, title, author, date, article, ticker_symbols)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (url) DO NOTHING
        """, (url, result.get('title'), result.get('author'), result.get('date'), 
              result.get('article'), json.dumps(result.get('ticker_symbols'))))
        conn.commit()
        cur.close()

        print(f"Article scraped and stored: {url}")
    else:
        print(f"Error scraping article {url}: {response.text}")

def main():
    dbname = "cryptonews"
    user = "postgres"
    password = "postgres"
    host = "127.0.0.1"
    csv_file = "crypto_links.csv"

    create_database_if_not_exists(dbname, user, password, host)
    
    conn = psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host
    )
    print("Initializing table")
    initialize_table(conn)

    print("Initializing Chromedriver")
    options = uc.ChromeOptions()
    options.add_argument('--blink-settings=imagesEnabled=false')
    driver = uc.Chrome(options=options)

    try:
        while True:
            try:
                scrape_and_store(conn, driver, csv_file)
            except Exception as e:
                print(f"Error occurred: {e}")
            time.sleep(15)  # Wait for 15 seconds
    except KeyboardInterrupt:
        print("Program manually terminated.")
    finally:
        conn.close()
        driver.quit()

if __name__ == "__main__":
    main()