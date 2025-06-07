import streamlit as st
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Streamlit UI
st.set_page_config(page_title="LinkedIn Multi-Post Scraper", layout="wide")
st.title("🔍 LinkedIn Post Scraper ")
st.write("This tool will help you to scrape your post and change it in json format")

# Inputs
with st.form("scraper_form"):
    email = st.text_input("LinkedIn Email")
    password = st.text_input("Password", type="password")
    profile_url = st.text_input("Profile URL", placeholder="https://www.linkedin.com/in/username/")
    submit = st.form_submit_button("Scrape Posts")

# Selenium Setup
@st.cache_resource
def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def login(driver, email, password):
    try:
        driver.get("https://www.linkedin.com/login")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username"))).send_keys(email)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(3)
        return "feed" in driver.current_url
    except Exception as e:
        st.error(f"Login failed: {str(e)}")
        return False

def scrape_posts(driver, url):
    driver.get(url)
    time.sleep(3)

    # Scroll multiple times to load posts
    last_height = 0
    scroll_attempts = 0
    required_posts = 10

    while scroll_attempts < 5:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            scroll_attempts += 1
        last_height = new_height

        # Check if we have enough posts
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        posts = soup.find_all('div', {'class': 'feed-shared-update-v2'})
        if len(posts) >= required_posts:
            break

    # Process the posts
    result = []
    for post in posts[:required_posts]:
        try:
            text = post.find('div', {'class': 'feed-shared-update-v2__description'}).get_text('\n', strip=True)
            likes = post.find('span', {'class': 'social-details-social-counts__reactions-count'})
            likes_count = int(likes.get_text(strip=True).replace(',', '')) if likes else 0

            result.append({
                "text": text,
                "engagement": likes_count
            })
        except Exception as e:
            st.warning(f"Skipped a post due to error: {str(e)}")
            continue

    return result

# Main Execution
if submit and profile_url:
    if "linkedin.com/in/" not in profile_url:
        st.error("Invalid LinkedIn URL")
    else:
        driver = get_driver()
        try:
            if login(driver, email, password):
                with st.spinner("Scraping posts (this may take 20-30 seconds)..."):
                    posts = scrape_posts(driver, profile_url)

                    if posts:
                        st.success(f"Successfully scraped {len(posts)} posts!")

                        # Display first 3 posts as sample
                        for i, post in enumerate(posts[:3], 1):
                            st.write(f"**Post {i}** ({post['engagement']} likes)")
                            st.write(post['text'])
                            st.write("---")

                        # Download all posts as JSON
                        st.download_button(
                            label="Download All Posts as JSON",
                            data=json.dumps(posts, indent=2),
                            file_name="linkedin_posts.json",
                            mime="application/json"
                        )
                    else:
                        st.error("Failed to scrape posts")
            else:
                st.error("Login failed - check credentials")
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
        finally:
            driver.quit()

st.markdown("---")
st.caption("Note: priya Upbhokta, ye ek data collection tool hai jiska maksad kisi ko personally harm krna nahi hai :D dhanyawad!")