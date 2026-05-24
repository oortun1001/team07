import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import re
from concurrent.futures import ThreadPoolExecutor
import plotly.express as px


def fetch_yogiyo_html(target_address, category_name):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
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
        return None
    finally:
        driver.quit()


def extract_store_details(html, category_name):
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    stores_data = []
    restaurant_items = soup.find_all("table", class_="item")

    for item in restaurant_items:
        name_element = item.find("div", class_="restaurant-name")
        star_element = item.find("span", class_="ico-star1")
        review_element = item.find("span", class_="review_num")

        if name_element:
            store_name = name_element.get_text().strip()
            rating = re.sub(r'[^0-9.]', '', star_element.get_text()) if star_element else None  # 결측치 처리를 위해 None 설정
            review_count = re.sub(r'[^0-9]', '', review_element.get_text()) if review_element else None

            stores_data.append({
                "가게명": store_name,
                "카테고리": category_name,
                "별점": float(rating) if rating else None,
                "리뷰 수": int(review_count) if review_count else None
            })
    return stores_data


def main():
    st.set_page_config(layout="wide")
    st.title("요기요 데이터 마이닝 및 시각화 최종 플랫폼")
    address_input = st.text_input("주소지 입력:", value="부산광역시 금정구 부산대학로63번길 2")

    if st.button("종합 분석 가동"):
        categories = ["치킨", "피자/양식", "중국집"]

        st.info("고속 병렬 데이터 엔진 가동 중...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            html_results = list(executor.map(lambda cat: fetch_yogiyo_html(address_input, cat), categories))

        all_stores = []
        for cat, html in zip(categories, html_results):
            all_stores.extend(extract_store_details(html, cat))

        df = pd.DataFrame(all_stores)

        if not df.empty:
            # 1. 중복 데이터 제거
            df = df.drop_duplicates(subset=["가게명", "카테고리"]).reset_index(drop=True)

            # 2. 데이터 전처리 (결측치는 각 카테고리의 중간값(Median)으로 보정)
            st.write("🔧 **데이터 정제 프로세스 가동:** 수집 누락된 별점/리뷰 수를 카테고리별 중간값으로 보정합니다.")
            df["별점"] = df.groupby("카테고리")["별점"].transform(lambda x: x.fillna(x.median()))
            df["리뷰 수"] = df.groupby("카테고리")["리뷰 수"].transform(lambda x: x.fillna(x.median())).astype(int)

            st.success(f"🎉 총 {len(df)}개의 고품질 데이터 정제 및 최종 로드 완료!")

            # 대시보드 레이아웃 분할
            col1, col2 = st.columns([4, 6])

            with col1:
                st.subheader("📋 최종 데이터 분석 테이블")
                st.dataframe(df)

                # ✨ 핵심 추가 기능: CSV 파일 다운로드 버튼 구현
                csv = df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="📥 분석 데이터 CSV 다운로드",
                    data=csv,
                    file_name="yogiyo_final_analysis.csv",
                    mime="text/csv"
                )

            with col2:
                st.subheader("📊 카테고리별 평균 평점 (정제 데이터 기준)")
                avg_rating = df.groupby("카테고리")["별점"].mean().reset_index()
                fig = px.bar(avg_rating, x="카테고리", y="별점", color="카테고리", text_auto=".2f",
                             labels={"별점": "평균 평점"}, template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.subheader("📈 가게별 평점 및 리뷰 수 종합 분포도")
            fig2 = px.scatter(df, x="가게명", y="리뷰 수", size="리뷰 수", color="별점",
                              hover_name="가게명", size_max=35, color_continuous_scale=px.colors.sequential.Viridis)
            st.plotly_chart(fig2, use_container_width=True)

        else:
            st.warning("수집된 데이터가 없습니다.")


if __name__ == "__main__":
    main()