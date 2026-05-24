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


def fetch_category_html(driver, category_index, category_name):
    """
    이미 주소가 설정된 상태의 브라우저(driver)에서
    지정된 순번(li)의 카테고리 탭을 클릭하고 동기화 대기 후 HTML을 반환합니다.
    """
    try:
        # 상단 메뉴 바 내부의 자식 요소 순번(li 태그 순서)을 이용해 선택합니다.
        target_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH,
                                        f"//ul[contains(@class, 'category') or contains(@class, 'nav')]/li[{category_index}] | //*[contains(@class, 'category-list')]/div[{category_index}]"))
        )
        target_tab.click()
        time.sleep(3)

        # 데이터가 렌더링될 때까지 동기화 대기
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CLASS_NAME, "restaurant-name"))
            )
        except:
            pass

        # 아래쪽 숨겨진 매장 리스트까지 불러오기 위해 스크롤 다운
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(1.5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

        return driver.page_source
    except Exception as e:
        st.warning(f"[{category_name}] 카테고리 화면 이동 중 지연이 발생했습니다.")
        return driver.page_source


def extract_store_details(html, category_name):
    """
    제공해주신 F12 구조를 기반으로 가게명, 별점, 리뷰 수를 세트로 추출하고
    해당 데이터의 카테고리명도 함께 기록합니다.
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


def crawl_all_categories(target_address):
    """
    한 번의 브라우저 실행으로 주소를 설정한 뒤,
    치킨(4), 피자/양식(5), 중국집(6)을 순서대로 순회하며 크롤링합니다.
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

    all_results = []

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        # GPS 가짜 좌표 주입 (부산대 정문)
        busan_univ_lat = 35.23553
        busan_univ_lng = 129.08312
        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
            "latitude": busan_univ_lat,
            "longitude": busan_univ_lng,
            "accuracy": 100
        })

        # 1. 요기요 메인페이지 접속 및 주소 검색 설정
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

        # 2. [핵심 요구사항] 3개 카테고리 연속 자동 크롤링 루프 수행
        # (순서: 치킨=4번째 탭, 피자/양식=5번째 탭, 중국집=6번째 탭)
        target_categories = [
            {"index": 4, "name": "치킨"},
            {"index": 5, "name": "피자/양식"},
            {"index": 6, "name": "중국집"}
        ]

        for cat in target_categories:
            st.write(f"🔄 현재 [{cat['name']}] 카테고리 데이터를 가져오는 중...")
            category_html = fetch_category_html(driver, cat["index"], cat["name"])

            if category_html:
                cat_data = extract_store_details(category_html, cat["name"])
                all_results.extend(cat_data)
                st.write(f"✅ [{cat['name']}] 수집 완료 (발견된 매장: {len(cat_data)}개)")

        driver.quit()
        return all_results

    except Exception as e:
        st.error(f"브라우저 자동화 실행 중 에러가 발생했습니다: {e}")
        if 'driver' in locals():
            driver.quit()
        return None


def main():
    st.title("요기요 3대 카테고리 통합 수집기 🍗🍕🇨🇳")
    st.write("버튼을 한 번만 누르면 '치킨', '피자/양식', '중국집' 매장 정보를 싹 다 모아서 동시에 보여줍니다.")

    # 텍스트 입력창 초기값 세팅 (사용자가 바로 수정 가능)
    default_address = "부산광역시 금정구 부산대학로63번길 2"
    address_input = st.text_input("데이터를 수집할 대상 주소지 입력:", value=default_address, key="address_input")

    if st.button("통합 크롤링 시작"):
        if not address_input.strip():
            st.warning("주소를 입력해 주세요.")
            return

        # 결과물을 보관할 세션 스테이트 초기화 및 로딩 가이드 출력
        st.info(f"실제 크롬 창을 켜서 '{address_input}' 주변의 치킨, 피자, 중국집 목록을 순차적으로 크롤링합니다. 약 30~40초가 소요됩니다.")

        # 3대 카테고리 연속 자동 수집 작동
        total_stores_list = crawl_all_categories(address_input)

        if total_stores_list:
            # 전체 수집 완료 후 판다스 데이터프레임화 및 정제
            df_result = pd.DataFrame(total_stores_list)

            # 다른 카테고리에 동일한 매장 이름이 중복 등록된 경우 처리 (가게명+카테고리 기준 중복 제거)
            df_result = df_result.drop_duplicates(subset=["가게명", "카테고리"], keep="first")

            st.success(f"🎉 모든 카테고리 수집 완료! 총 {len(df_result)}곳의 매장 상세 정보를 확보했습니다.")

            # 별점 및 리뷰 수 순서대로 통합 정렬
            df_sorted = df_result.sort_values(by=["별점", "리뷰 수"], ascending=False).reset_index(drop=True)
            df_sorted.index = df_sorted.index + 1  # 연번 1번부터 매칭

            # 결과를 Streamlit 격자 표로 동시 출력
            st.dataframe(df_sorted, use_container_width=True)

            # 외부 저장을 위한 엑셀(CSV) 다운로드 기능 지원
            csv_data = df_sorted.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="통합 수집 결과 엑셀(CSV) 파일로 저장하기",
                data=csv_data,
                file_name=f"요기요_통합_리스트_{address_input[:10]}.csv",
                mime="text/csv"
            )
        else:
            st.error("가게 목록 화면 이동은 끝났으나 데이터를 추출하지 못했습니다. HTML 구조 점검이 필요합니다.")


if __name__ == "__main__":
    main()