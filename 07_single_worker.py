import sys
import json
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def initialize_browser(headless, no_images, no_javascript, zoom, no_autoplay, timeout):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    if no_images:
        options.add_argument('--blink-settings=imagesEnabled=false')
    if no_javascript:
        options.add_argument('--disable-javascript')
    if no_autoplay:
        options.add_argument('--autoplay-policy=user-gesture-required')
    # options.add_argument(f'--force-device-scale-factor={zoom}')
    
    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(timeout)
    return driver

def main():
    args = json.loads(sys.argv[1])
    driver = initialize_browser(
        headless=args.get('headless', False),
        no_images=args.get('no_images', True),
        no_javascript=args.get('no_javascript', True),
        zoom=args.get('zoom', 0.1),
        no_autoplay=args.get('no_autoplay', True),
        timeout=args.get('timeout', 30)
    )

    try:
        while True:
            url = sys.stdin.readline().strip()
            if not url:
                time.sleep(0.1)
                continue

            try:
                driver.get(url)
                driver.execute_script(f"document.body.style.zoom = '{0.1}'")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                
                # Wait a bit for the zoom to take effect
                time.sleep(0.5)
                html = driver.page_source
                print(json.dumps({"url": url, "html": html}))
                sys.stdout.flush()
            except Exception as e:
                print(json.dumps({"url": url, "error": str(e)}), file=sys.stderr)
                sys.stderr.flush()

    except KeyboardInterrupt:
        pass
    finally:
        driver.quit()

if __name__ == "__main__":
    main()