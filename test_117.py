import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import concurrent.futures
import plotly.express as px  # Y축 고정 및 정밀 시각화를 위한 라이브러리


def fetch_yogiyo_html(target_address, category_name):
    """
    원본 브라우저 구동 스크립트 형태를 100% 그대로 유지합니다.
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    prefs = {"profile.default_content_setting_values.geolocation": 2}
    chrome_options.add_experimental_option("prefs", prefs)

    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        busan_univ_lat = 35.23553
        busan_univ_lng = 129.08312
        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
            "latitude": busan_univ_lat,
            "longitude": busan_univ_lng,
            "accuracy": 100
        })

        driver.get("https://www.yogiyo.co.kr/")
        time.sleep(3)

        search_box = None
        selectors = ["input[name='address_input']", "input.form-control", "input[placeholder*='주소']"]
        for selector in selectors:
            try:
                search_box = driver.find_element(By.CSS_SELECTOR, selector)
                if search_box.is_displayed():
                    break
            except:
                continue

        if not search_box:
            driver.quit()
            return None

        search_box.click()
        search_box.clear()
        search_box.send_keys(target_address)
        time.sleep(1)
        search_box.send_keys(Keys.ENTER)
        time.sleep(3)

        try:
            dropdown_item = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//*[contains(text(), '부산대학로')] | //a[contains(@class, 'list-group-item')][1]"))
            )
            dropdown_item.click()
            time.sleep(4)
        except:
            pass

        try:
            if category_name == "치킨":
                target_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//ul[contains(@class, 'category') or contains(@class, 'nav')]/li[4] | //*[contains(@class, 'category-list')]/div[4]"))
                )
            elif category_name == "피자/양식":
                target_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//ul[contains(@class, 'category') or contains(@class, 'nav')]/li[5] | //*[contains(@class, 'category-list')]/div[5]"))
                )
            elif category_name == "중국집":
                target_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//ul[contains(@class, 'category') or contains(@class, 'nav')]/li[6] | //*[contains(@class, 'category-list')]/div[6]"))
                )

            target_tab.click()
            time.sleep(3)
        except Exception:
            try:
                backup_xpath = f"//*[contains(text(), '{category_name.split('/')[0]}')]"
                target_tab = driver.find_element(By.XPATH, backup_xpath)
                target_tab.click()
                time.sleep(3)
            except Exception as e:
                st.error(f"화면에서 '{category_name}' 카테고리 버튼을 인식하지 못했습니다: {e}")
                driver.quit()
                return None

        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CLASS_NAME, "restaurant-name"))
            )
        except:
            pass

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        html = driver.page_source
        driver.quit()
        return html

    except Exception as e:
        st.error(f"브라우저 자동화 실행 중 에러가 발생했습니다: {e}")
        if 'driver' in locals():
            driver.quit()
        return None


def extract_store_details(html, category_name):
    """
    원본 데이터 파싱 구조를 유지합니다.
    """
    soup = BeautifulSoup(html, "html.parser")
    stores_data = []

    restaurant_items = soup.find_all("table", class_="item") or soup.find_all("div", class_="col-sm-6")

    if not restaurant_items:
        names = [div.get_text().strip() for div in soup.find_all("div", class_="restaurant-name")]
        return [{"가게명": name, "카테고리": category_name, "별점": 0.0, "리뷰 수": 0} for name in names]

    for item in restaurant_items:
        name_element = item.find("div", class_="restaurant-name")
        if not name_element:
            continue
        store_name = name_element["title"].strip() if name_element.has_attr(
            "title") else name_element.get_text().strip()

        star_element = item.find("span", class_="ico-star1")
        if star_element:
            star_text = star_element.get_text().strip()
            rating = re.sub(r'[^0-9.]', '', star_text)
        else:
            rating = "0.0"

        review_element = item.find("span", class_="review_num")
        if review_element:
            review_text = review_element.get_text().strip()
            review_count = re.sub(r'[^0-9]', '', review_text)
        else:
            review_count = "0"

        if store_name:
            stores_data.append({
                "가게명": store_name,
                "카테고리": category_name,
                "별점": float(rating) if rating else 0.0,
                "리뷰 수": int(review_count) if review_count else 0
            })

    return stores_data


def thread_worker(address, category):
    """
    IP 차단 방지용 시차 스레드 워커입니다.
    """
    if category == "피자/양식":
        time.sleep(1.5)
    elif category == "중국집":
        time.sleep(3.0)

    html = fetch_yogiyo_html(address, category)
    if html:
        return extract_store_details(html, category)
    return []


def main():
    st.title("요기요 3대 업종 통합 수집 및 시각화 대시보드 🚀")
    st.write("크롬 창 3개를 동시에 띄워 데이터를 완벽 수집한 뒤, Y축 범위가 고정된 상관관계 산점도를 그려냅니다.")

    default_address = "부산광역시 금정구 부산대학로63번길 2"
    address_input = st.text_input("데이터를 수집할 대상 주소지 입력:", value=default_address, key="address_input")

    if st.button("통합 크롤링 시작"):
        if not address_input.strip():
            st.warning("주소를 입력해 주세요.")
            return

        st.info("🔥 멀티스레딩(병렬 처리) 가동! 3개의 독립 브라우저가 개별 기동됩니다. (약 15~20초 소요)")

        categories_to_crawl = ["치킨", "피자/양식", "중국집"]
        all_combined_stores = []

        # 백그라운드 병렬 처리 기동
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(thread_worker, address_input, cat) for cat in categories_to_crawl]
            for future in concurrent.futures.as_completed(futures):
                try:
                    result_data = future.result()
                    if result_data:
                        all_combined_stores.extend(result_data)
                except Exception as e:
                    st.error(f"데이터 수집 중 에러 발생: {e}")

        if all_combined_stores:
            df_result = pd.DataFrame(all_combined_stores)

            # [중복 제거 기준] 가게 이름이 같다면 카테고리가 달라도 무조건 중복 제거! (단일화 필터 유지)
            df_result = df_result.drop_duplicates(subset=["가게명"], keep="first")

            st.success(f"🎉 중복 제거 완료! 여러 카테고리에 걸쳐있던 가게들을 묶어 총 {len(df_result)}곳의 순수 매장만 확보했습니다.")

            # 별점 및 리뷰 수 기준 내림차순 정렬
            df_sorted = df_result.sort_values(by=["별점", "리뷰 수"], ascending=False).reset_index(drop=True)
            df_sorted.index = df_sorted.index + 1

            # 1. 테이블(표) 화면 출력
            st.dataframe(df_sorted, use_container_width=True)

            # 💡 [요구사항 반영] 2. Plotly를 활용한 별점 범위(0~5점) 완벽 고정 산점도 출력
            st.subheader("📊 리뷰 수와 별점의 상관관계 분포도 (별점 0~5점 고정)")

            # Plotly 산점도 생성 (가게명은 hover 데이터에서도 원천 제외하여 순수 상관관계만 노출)
            fig = px.scatter(
                df_sorted,
                x="리뷰 수",
                y="별점",
                color="카테고리",
                labels={"리뷰 수": "리뷰 수 (개)", "별점": "평점 (별점)"},
                range_y=[0.0, 5.2],  # 🌟 별점 0점부터 5점까지 Y축 범위를 강제로 물리적 고정 (가독성을 위해 5.2까지 세팅)
                title="상권 내 업종별 평점 및 리뷰 분포 현황"
            )

            # 차트 스타일 세밀 조정 (디자인 깔끔화)
            fig.update_layout(
                hovermode="closest",
                legend_title_text="업종 분류",
                template="plotly_white"
            )

            # Streamlit 화면에 Plotly 차트 삽입
            st.plotly_chart(fig, use_container_width=True)

            # 3. 단일 통합 마스터 엑셀(CSV) 내보내기
            csv_data = df_sorted.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📁 중복 없는 통합 마스터 엑셀(CSV) 다운로드",
                data=csv_data,
                file_name="요기요_3대업종_순수매장_통합마스터.csv",
                mime="text/csv"
            )
        else:
            st.error("가게 데이터를 추출하지 못했습니다. 주소 혹은 요기요 사이트 상태를 점검해 주세요.")


if __name__ == "__main__":
    main()