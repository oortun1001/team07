import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import re


def fetch_yogiyo_html(target_address, category_name):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get("https://www.yogiyo.co.kr/")
        time.sleep(3)

        search_box = driver.find_element(By.CSS_SELECTOR, "input[name='address_input']")
        search_box.click()
        search_box.clear()
        search_box.send_keys(target_address)
        time.sleep(1)
        search_box.send_keys(Keys.ENTER)
        time.sleep(3)

        try:
            dropdown_item = driver.find_element(By.XPATH, "//*[contains(text(), '부산대학로')]")
            dropdown_item.click()
            time.sleep(3)
        except:
            pass

        if category_name == "치킨":
            idx = 4
        elif category_name == "피자/양식":
            idx = 5
        else:
            idx = 6

        target_tab = driver.find_element(By.XPATH, f"//ul[contains(@class, 'category')]/li[{idx}]")
        target_tab.click()
        time.sleep(3)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        return driver.page_source
    except Exception as e:
        st.error(f"에러 발생: {e}")
        return None
    finally:
        driver.quit()


def extract_store_details(html, category_name):
    soup = BeautifulSoup(html, "html.parser")
    stores_data = []
    restaurant_items = soup.find_all("table", class_="item")

    for item in restaurant_items:
        name_element = item.find("div", class_="restaurant-name")
        star_element = item.find("span", class_="ico-star1")
        review_element = item.find("span", class_="review_num")

        if name_element:
            store_name = name_element.get_text().strip()
            rating = re.sub(r'[^0-9.]', '', star_element.get_text()) if star_element else "0.0"
            review_count = re.sub(r'[^0-9]', '', review_element.get_text()) if review_element else "0"

            stores_data.append({
                "가게명": store_name,
                "카테고리": category_name,
                "별점": float(rating) if rating else 0.0,
                "리뷰 수": int(review_count) if review_count else 0
            })
    return stores_data


def main():
    st.title("요기요 데이터 수집기 (기본형)")
    address_input = st.text_input("주소지 입력:", value="부산광역시 금정구 부산대학로63번길 2")

    if st.button("크롤링 시작"):
        categories = ["치킨", "피자/양식", "중국집"]
        all_stores = []
        for cat in categories:
            html = fetch_yogiyo_html(address_input, cat)
            if html:
                all_stores.extend(extract_store_details(html, cat))

        df = pd.DataFrame(all_stores)
        st.dataframe(df)


if __name__ == "__main__":
    main()