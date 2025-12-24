from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time
import re

import os

app = Flask(__name__)
# CORS: Allow Localhost (Frontend) and Render Domains
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "https://*.onrender.com"]}})

def setup_driver():
    chrome_options = Options()
    # Headless Options for Server Environment
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=2560,1440")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

@app.route('/api/scrape', methods=['POST'])
def scrape_mt5():
    data = request.json
    login_id = data.get('login')
    password = data.get('password')
    # Mock Decryption for Phase 1
    if password and password.startswith('NOT_SECURE_'):
        password = password.replace('NOT_SECURE_', '')
    server_name = data.get('server') 
    
    driver = None
    try:
        driver = setup_driver()
        print("Driver launched.")
        
        # 1. Force English
        driver.get("https://web.metatrader.app/terminal?lang=en")
        wait = WebDriverWait(driver, 30)
        time.sleep(5)
        
        # Cookies
        try: driver.find_element(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'OK')]").click()
        except: pass
            
        # Login
        try: driver.find_element(By.NAME, "login")
        except:
            try:
                wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@title='Menu']"))).click()
                time.sleep(1)
                wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Connect to Account') or contains(text(), 'Manage accounts') or contains(text(), 'File')]"))).click()
                try: driver.find_element(By.XPATH, "//div[contains(text(), 'Connect to Account')]").click()
                except: pass
            except: pass

        # Credentials
        wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='login']"))).send_keys(login_id)
        driver.find_element(By.XPATH, "//input[@name='password']").send_keys(password)
        try:
            srv = driver.find_element(By.XPATH, "//input[@name='server']")
            srv.clear()
            srv.send_keys(server_name)
            time.sleep(1)
            srv.send_keys(Keys.RETURN)
        except: pass
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        print("Submitted.")
        
        # Wait for History
        history_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@title='History' or contains(text(), 'History')]")))
        history_tab.click()
        time.sleep(5)
        
        # *** ZOOM OUT STRATEGY ***
        driver.execute_script("document.body.style.zoom = '50%'")
        time.sleep(2)

        # --- SURGICAL 'ALL HISTORY' ---
        try:
            time_header = driver.find_element(By.XPATH, "//div[contains(@class, 'th') and contains(text(), 'Time')]")
            ActionChains(driver).context_click(time_header).perform()
            time.sleep(1)
        except:
            try:
                actions = ActionChains(driver)
                win = driver.get_window_size()
                actions.move_by_offset(win['width']/2, win['height']/2 + 100).context_click().perform()
                time.sleep(1)
            except: pass
        
        try:
            wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'Request all history') or contains(text(), 'All history')]"))).click()
            print("Request All History: CLICKED")
            time.sleep(10)
        except Exception as e:
            print(f"Request All History Click Failed: {e}")

        # --- DATA HARVEST (KITCHEN SINK SCROLL) ---
        print("Starting Kitchen Sink Scroll Loop...")
        all_trades_dict = {}
        
        # Header Map
        header_map = {}
        default_map = {'time': 0, 'ticket': 1, 'symbol': 2, 'type': 3, 'volume': 4, 'openPrice': 5, 'sl': 6, 'tp': 7, 'closePrice': 8, 'profit': 11}
        try:
            headers = driver.find_elements(By.CSS_SELECTOR, ".th")
            temp_map = {}
            price_indices = []
            for i, h in enumerate(headers):
                t = h.get_attribute("textContent").strip().lower()
                if not t: continue
                if 'time' in t and 'time' not in temp_map: temp_map['time'] = i
                elif 'ticket' in t: temp_map['ticket'] = i
                elif 'symbol' in t: temp_map['symbol'] = i
                elif 'type' in t: temp_map['type'] = i
                elif 'profit' in t: temp_map['profit'] = i
                elif 'volume' in t: temp_map['volume'] = i
                elif 'sl' == t or 's / l' in t: temp_map['sl'] = i
                elif 'tp' == t or 't / p' in t: temp_map['tp'] = i
                elif 'price' in t or 'prijs' in t: price_indices.append(i)
            
            if len(price_indices) >= 1: temp_map['openPrice'] = price_indices[0]
            if len(price_indices) >= 2: temp_map['closePrice'] = price_indices[1]
            if 'time' in temp_map: header_map = temp_map
            else: header_map = default_map
        except: header_map = default_map

        # IDENTIFY CONTAINER (JS)
        scroll_container = driver.execute_script("""
             var allDivs = document.querySelectorAll('div');
             for(var i=0; i<allDivs.length; i++){
                if(allDivs[i].scrollHeight > allDivs[i].clientHeight && allDivs[i].clientHeight > 50){
                    return allDivs[i];
                }
             }
             return null;
        """)

        # SCROLL LOOP
        last_count = 0 
        attempts = 0
        
        for i in range(50):
            rows = driver.find_elements(By.CSS_SELECTOR, ".tr")
            for r in rows:
                try:
                    cells = r.find_elements(By.CSS_SELECTOR, ".td")
                    txts = [c.get_attribute("textContent").strip() for c in cells]
                    
                    def get_val(k):
                        idx = header_map.get(k)
                        if idx is not None and idx < len(txts): return txts[idx]
                        return ""
                    
                    ticket = get_val('ticket')
                    # FILTER OUT JUNK/SUMMARY ROWS
                    if not ticket: continue
                    # Remove summary rows with ticket '#0.00' or similar
                    if ticket == '#0.00' or ticket == '0.00': continue
                    # Remove if ticket doesn't look like a trade ID (simple heuristic)
                    if not re.search(r'\d', ticket): continue
                    
                    if ticket in all_trades_dict: continue
                    
                    all_trades_dict[ticket] = {
                        "ticket": ticket, 
                        "openTime": get_val('time'),
                        "type": get_val('type'), 
                        "symbol": get_val('symbol'),
                        "profit": get_val('profit'), 
                        "volume": get_val('volume'),
                        "openPrice": get_val('openPrice'), 
                        "closePrice": get_val('closePrice'),
                        "sl": get_val('sl'), 
                        "tp": get_val('tp')
                    }
                except: pass
            
            total_collected = len(all_trades_dict)
            print(f"Loop {i}: Collected {total_collected} unique trades.")
            
            if total_collected > last_count:
                last_count = total_collected
                attempts = 0
            else:
                attempts += 1
            
            # Only check for stuck state after a few loops to allow initial load
            if i > 8 and attempts >= 3: 
                print("No new trades for 3 consecutive loops (after warmup). Done.")
                break

            # SCROLL ACTIONS
            if scroll_container:
                driver.execute_script("arguments[0].scrollTop += 500;", scroll_container)
            else:
                driver.execute_script("window.scrollBy(0, 500);")
            
            try: ActionChains(driver).scroll_by_amount(0, 500).perform()
            except: pass
            
            try:
                if rows:
                    target = rows[-1]
                    target.click()
                    ActionChains(driver).send_keys(Keys.PAGE_DOWN).perform()
            except: pass
            
            time.sleep(1.0)

        res = list(all_trades_dict.values())
        print(f"Final Count: {len(res)}")
        return jsonify({"trades": res})

    except Exception as e:
        print(f"CRITICAL: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if driver: driver.quit()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
