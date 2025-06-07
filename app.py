import json
import time
from flask import Flask, render_template, request, send_file, make_response
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import logging
from webdriver_manager.chrome import ChromeDriverManager
import os
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Selenium Setup
def get_driver():
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )

        # Set Chrome binary location explicitly
        chrome_binary_locations = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/lib/chromium-browser/chrome",
            "/usr/lib/chromium/chrome",
            "/opt/google/chrome/google-chrome",
            "/usr/local/bin/google-chrome",
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
        ]
        chrome_binary_found = False
        for binary_path in chrome_binary_locations:
            if os.path.exists(binary_path):
                chrome_options.binary_location = binary_path
                logger.info(f"Chrome binary found at: {binary_path}")
                chrome_binary_found = True
                break

        if not chrome_binary_found:
            logger.info("Checking Chrome version manually")
            chrome_version = os.popen("google-chrome --version").read()
            logger.info(f"Chrome version: {chrome_version}")
            error_msg = f"Chrome binary not found in standard locations. Checked: {', '.join(chrome_binary_locations)}"
            logger.error(error_msg)
            return None, error_msg

        # Use ChromeDriverManager to install ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(60)

        # Execute script to hide Selenium usage
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: 'undefined'
                });
            """
        })
        logger.info("WebDriver initialized successfully")
        return driver, None

    except Exception as e:
        error_msg = f"WebDriver initialization error: {str(e)} | Type: {type(e).__name__} | Traceback: {''.join(traceback.format_tb(e.__traceback__))}"
        logger.error(error_msg)
        return None, error_msg

def login(driver, email, password):
    try:
        driver.get("https://www.linkedin.com/login")
        logger.info("Navigating to LinkedIn login page")

        # Wait for email field with longer timeout
        email_field = WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        logger.info("Email field found")
        email_field.send_keys(email)

        # Enter password
        password_field = driver.find_element(By.ID, "password")
        password_field.send_keys(password)
        logger.info("Password entered")

        # Click submit
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_button.click()
        logger.info("Submit button clicked")

        # Wait for URL change with retry logic
        for _ in range(3):  # Retry up to 3 times
            try:
                WebDriverWait(driver, 60).until(
                    lambda d: "feed" in d.current_url or "security" in d.current_url or "error" in d.current_url or "challenge" in d.current_url
                )
                break
            except Exception as retry_e:
                logger.warning(f"Retry attempt failed: {str(retry_e)}")
                time.sleep(5)  # Wait before retry
        else:
            return False, "Login timed out after retries"

        current_url = driver.current_url
        logger.info(f"Current URL after login attempt: {current_url}")

        if "security" in current_url or "challenge" in current_url:
            return False, "LinkedIn requires additional security verification (e.g., CAPTCHA or 2FA). Automated login may not proceed."
        if "error" in current_url:
            return False, "Login failed: Invalid credentials or other issue."
        if "feed" in current_url:
            return True, None
        return False, f"Unexpected URL after login: {current_url}"

    except Exception as e:
        error_msg = f"Login error: {str(e)} | Type: {type(e).__name__} | Traceback: {''.join(traceback.format_tb(e.__traceback__))}"
        logger.error(error_msg)
        return False, error_msg
def scrape_posts(driver, url):
    try:
        logger.info("Navigating to profile URL: " + url)
        driver.get(url)
        logger.info("Waiting for page to load")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        logger.info("Page loaded successfully")

        # Scroll to load posts
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        required_posts = 10
        max_scroll_attempts = 10

        logger.info("Starting scroll to load posts")
        while scroll_attempts < max_scroll_attempts:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            logger.info(f"Scrolled to bottom, attempt {scroll_attempts + 1}")
            try:
                WebDriverWait(driver, 5).until(
                    lambda d: d.execute_script("return document.body.scrollHeight") > last_height
                )
            except Exception as e:
                logger.warning(f"Scroll wait failed: {str(e)}")
                scroll_attempts += 1
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
            last_height = new_height

            posts = driver.find_elements(By.CSS_SELECTOR, 'div.feed-shared-update-v2')
            logger.info(f"Found {len(posts)} posts so far")
            if len(posts) >= required_posts:
                break

        if not posts:
            logger.error("No posts found after scrolling")
            return None, "No posts found after scrolling. LinkedIn may have blocked access or the selector is outdated."

        # Process posts
        result = []
        logger.info("Processing posts")
        for i, post in enumerate(posts[:required_posts], 1):
            try:
                text_elements = post.find_elements(By.CSS_SELECTOR, 'div.feed-shared-update-v2__description')
                text = text_elements[0].text.strip() if text_elements else "No text available"
                logger.info(f"Post {i}: Text extracted - {text[:50]}...")

                likes_elements = post.find_elements(By.CSS_SELECTOR, 'span.social-details-social-counts__reactions-count')
                likes_count = 0
                if likes_elements:
                    likes_text = likes_elements[0].text.strip()
                    if likes_text:
                        try:
                            if 'K' in likes_text:
                                likes_count = int(float(likes_text.replace('K', '')) * 1000)
                            else:
                                likes_count = int(likes_text.replace(',', ''))
                        except ValueError as e:
                            logger.warning(f"Post {i}: Failed to parse likes '{likes_text}': {str(e)}")
                            likes_count = 0
                logger.info(f"Post {i}: Likes - {likes_count}")

                result.append({
                    "text": text,
                    "likes": likes_count
                })
            except Exception as e:
                logger.warning(f"Skipped post {i}: {str(e)}")
                continue

        logger.info(f"Successfully processed {len(result)} posts")
        return result, None
    except Exception as e:
        logger.error(f"Scraping error: {str(e)}")
        return None, f"Scraping error: {str(e)}"

# Flask Routes
@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    posts = None
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        profile_url = request.form.get('profile_url')

        if not all([email, password, password, profile_url]):
            error = "Please fill all fields"
            logger.error("Missing required fields")
        elif "linkedin.com/in/" not in profile_url:
            error = "Please enter a valid LinkedIn profile URL"
            logger.error("Invalid profile URL")
        else:
            logger.info(f"Starting scrape for {profile_url}")
            driver, driver_error = get_driver()
            if driver:
                try:
                    success, login_error = login(driver, email, password)
                    if success:
                        posts, scrape_error = scrape_posts(driver, profile_url)
                        if posts and len(posts) > 0:
                            with open('linkedin_posts.json', 'w') as f:
                                json.dump(posts, f, indent=2)
                            logger.info(f"Scraped {len(posts)} posts successfully")
                        else:
                            error = scrape_error or "No posts found or scraping failed"
                    else:
                        error = login_error or "Login failed"
                except Exception as e:
                    error = f"Error: {str(e)} | Type: {type(e).__name__}"
                    logger.error(f"Main execution error: {str(e)}")
                finally:
                    if driver:
                        driver.quit()
                        logger.info("WebDriver closed")
            else:
                error = driver_error or "WebDriver initialization failed"

    return render_template('index.html', error=error, posts=posts)
@app.route('/download')
def download():
    try:
        with open('linkedin_posts.json', 'r') as f:
            data = f.read()
        response = make_response(data)
        response.headers['Content-Disposition'] = 'attachment; filename=linkedin_posts.json'
        response.headers['Content-Type'] = 'application/json'
        return response
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return "Error generating download", 500

if __name__ == '__main__':
    app.run(debug=True)