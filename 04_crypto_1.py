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

def create_database_if_not_exists(dbname, user, password, host):
    conn = psycopg2.connect(
        dbname="postgres",  # Connect to the default "postgres" database
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
        print(f"Datenbank {dbname} wurde erstellt.")
    else:
        print(f"Datenbank {dbname} existiert bereits.")

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
    conn.commit()
    cur.close()

def scrape_and_store(conn, driver, csv_file):
    url = "https://finance.yahoo.com/topic/crypto/"
    driver.get(url)
    
    # Warten, bis die Seite geladen ist
    wait = WebDriverWait(driver, 3)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href]")))

    # Scrollen, um weitere Links zu laden
    scroll_pause_time = 1  # Pause zwischen jedem Scroll (in Sekunden)
    scroll_attempts = 3   # Anzahl der Scroll-Versuche
    
    for _ in range(scroll_attempts):
        # Seite nach unten scrollen
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
    print("initialize table")
    initialize_table(conn)

    print("initialize Chromedriver")
    # Undetected Chromedriver initialisieren
    options = uc.ChromeOptions()
    # options.add_argument("--headless")  # Optional: Headless-Modus aktivieren
    options.add_argument('--blink-settings=imagesEnabled=false')
    driver = uc.Chrome(options=options)

    try:
        while True:
            try:
                scrape_and_store(conn, driver, csv_file)
            except Exception as e:
                print(f"Error occurred: {e}")
            time.sleep(3)  # 10 Sekunden warten
    except KeyboardInterrupt:
        print("Programm wurde manuell beendet.")
    finally:
        conn.close()
        driver.quit()

if __name__ == "__main__":
    main()