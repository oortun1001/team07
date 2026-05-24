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


def fetch_yogiyo_html(target_address, category_name):
    """
    브라우저의 실제 GPS 추적을 차단하고 부산대 좌표를 강제 주입한 뒤,
    선택된 카테고리 화면이 완전히 렌더링될 때까지 동기화 대기 후 HTML을 반환합니다.
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # 1. 노트북의 실제 위치(명륜동) 간섭을 막기 위해 브라우저 자체 Geolocation 권한 거부
    prefs = {"profile.default_content_setting_values.geolocation": 2}
    chrome_options.add_experimental_option("prefs", prefs)

    # 자동화 탐지 차단 방지 옵션
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        # 2. 하드웨어 레벨에서 브라우저 GPS를 부산대 정문 좌표로 고정
        busan_univ_lat = 35.23553
        busan_univ_lng = 129.08312
        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
            "latitude": busan_univ_lat,
            "longitude": busan_univ_lng,
            "accuracy": 100
        })

        # 3. 요기요 메인페이지 접속
        driver.get("https://www.yogiyo.co.kr/")
        time.sleep(3)

        # 4. 주소 검색창 탐색 및 주소 타이핑 입력
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

        # 5. 연관 검색 주소 결과 목록에서 첫 번째 항목 클릭
        try:
            dropdown_item = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//*[contains(text(), '부산대학로')] | //a[contains(@class, 'list-group-item')][1]"))
            )
            dropdown_item.click()
            time.sleep(4)
        except:
            pass

        # 6. [구조 보완] 보내주신 이미지 기반 상단 카테고리 바 순서 정밀 타격 클릭
        # 글자 분싱 대신 상단 메뉴 바 내부의 자식 요소 순번(li 태그 순서)을 이용해 오차 없이 선택합니다.
        try:
            if category_name == "치킨":
                # 4번째 카테고리 탭 클릭
                target_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//ul[contains(@class, 'category') or contains(@class, 'nav')]/li[4] | //*[contains(@class, 'category-list')]/div[4]"))
                )
            elif category_name == "피자/양식":
                # 5번째 카테고리 탭 클릭 (특수문자 에러 원천 차단)
                target_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//ul[contains(@class, 'category') or contains(@class, 'nav')]/li[5] | //*[contains(@class, 'category-list')]/div[5]"))
                )
            elif category_name == "중국집":
                # 6번째 카테고리 탭 클릭
                target_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//ul[contains(@class, 'category') or contains(@class, 'nav')]/li[6] | //*[contains(@class, 'category-list')]/div[6]"))
                )

            target_tab.click()
            time.sleep(3)
        except Exception:
            # 순번 선택 백업용: 이미지 목록 텍스트 기반 2차 탐색 트라이
            try:
                backup_xpath = f"//*[contains(text(), '{category_name.split('/')[0]}')]"
                target_tab = driver.find_element(By.XPATH, backup_xpath)
                target_tab.click()
                time.sleep(3)
            except Exception as e:
                st.error(f"화면에서 '{category_name}' 카테고리 버튼을 인식하지 못했습니다: {e}")
                driver.quit()
                return None

        # 7. [동기화 핵심] F12 확인본 구조인 'restaurant-name'이 렌더링될 때까지 대기
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CLASS_NAME, "restaurant-name"))
            )
        except:
            pass

        # 아래쪽 숨겨진 매장 리스트까지 불러오기 위해 스크롤 다운
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        # 완성된 HTML 소스 추출 및 종료
        html = driver.page_source
        driver.quit()
        return html

    except Exception as e:
        st.error(f"브라우저 자동화 실행 중 에러가 발생했습니다: {e}")
        if 'driver' in locals():
            driver.quit()
        return None


def extract_store_details(html):
    """
    제공해주신 F12 캡쳐 화면 구조(restaurant-name, ico-star1, review_num)에
    정확히 매칭하여 가게명, 별점, 리뷰 수를 리스트 구조로 정제하여 반환합니다.
    """
    soup = BeautifulSoup(html, "html.parser")
    stores_data = []

    # 각 가게 정보 섹션을 감싸고 있는 개별 부모 테이블/박스 수집
    restaurant_items = soup.find_all("table", class_="item") or soup.find_all("div", class_="col-sm-6")

    if not restaurant_items:
        # 부모 노드 분할이 실패할 경우 단순 나열 데이터로 백업 추출 수행
        names = [div.get_text().strip() for div in soup.find_all("div", class_="restaurant-name")]
        return [{"가게명": name, "별점": 0.0, "리뷰 수": 0} for name in names]

    for item in restaurant_items:
        # 1. 가게명 파싱 (div.restaurant-name)
        name_element = item.find("div", class_="restaurant-name")
        if not name_element:
            continue
        store_name = name_element["title"].strip() if name_element.has_attr(
            "title") else name_element.get_text().strip()

        # 2. 별점 파싱 (span.ico-star1)
        star_element = item.find("span", class_="ico-star1")
        if star_element:
            star_text = star_element.get_text().strip()
            rating = re.sub(r'[^0-9.]', '', star_text)  # 문자열 내 숫자와 마침표만 남김
        else:
            rating = "0.0"

        # 3. 리뷰 수 파싱 (span.review_num)
        review_element = item.find("span", class_="review_num")
        if review_element:
            review_text = review_element.get_text().strip()
            review_count = re.sub(r'[^0-9]', '', review_text)  # 문자열 내 숫자만 남김
        else:
            review_count = "0"

        # 매칭 데이터 저장
        if store_name:
            stores_data.append({
                "가게명": store_name,
                "별점": float(rating) if rating else 0.0,
                "리뷰 수": int(review_count) if review_count else 0
            })

    # 데이터프레임 변환 후 가게명 기준 중복 데이터 제거
    df = pd.DataFrame(stores_data)
    if not df.empty:
        df = df.drop_duplicates(subset=["가게명"], keep="first")
        return df.to_dict(orient="records")
    return stores_data


def main():
    """
    Streamlit 웹 UI 구성 및 제어 인터페이스 메인 함수
    """
    st.title("요기요 카테고리별 상세 정보 수집기")
    st.write("지정한 주소지의 가게명, 별점, 리뷰 수를 카테고리별로 정밀 수집합니다.")

    # 텍스트 입력창 초기값 세팅 (사용자가 바로 수정 가능)
    default_address = "부산광역시 금정구 부산대학로63번길 2"
    address_input = st.text_input("데이터를 수집할 대상 주소지 입력:", value=default_address, key="address_input")

    # [추가] 원하는 카테고리를 직관적으로 선택할 수 있는 라디오 버튼 구성
    category_list = ["치킨", "피자/양식", "중국집"]
    selected_category = st.radio("크롤링할 카테고리를 선택하세요:", category_list, horizontal=True)

    # 크롤링 시작 버튼 클릭 시 로직 구동
    if st.button("크롤링 시작"):
        if not address_input.strip():
            st.warning("주소를 입력해 주세요.")
            return

        st.info(f"실제 크롬 드라이버를 기동하여 위치 우회 및 [{selected_category}] 매장 목록을 로드하고 있습니다...")

        # 1. 셀레늄을 통한 동적 데이터 웹 수집
        html_content = fetch_yogiyo_html(address_input, selected_category)

        if html_content:
            # 2. 뷰티풀수프를 통한 별점/리뷰 정보 상세 정밀 파싱
            final_stores_list = extract_store_details(html_content)

            # 3. 결과 출력 레이아웃 생성
            if final_stores_list:
                st.success(
                    f"성공! '{address_input}' 주변 [{selected_category}] 카테고리 매장 총 {len(final_stores_list)}곳의 정보를 확보했습니다.")

                # 표 데이터 가독성을 위한 판다스 데이터프레임화
                df_result = pd.DataFrame(final_stores_list)

                # 별점 및 리뷰 수 기준 내림차순 정렬 기능 탑재하여 표 출력
                df_sorted = df_result.sort_values(by=["별점", "리뷰 수"], ascending=False).reset_index(drop=True)
                df_sorted.index = df_sorted.index + 1  # 인덱스 번호를 1번부터 시작하도록 설정
                st.dataframe(df_sorted, use_container_width=True)

                # 4. 외부 저장을 위한 엑셀(CSV) 다운로드 기능 연동
                csv_data = df_sorted.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label=f"[{selected_category}] 수집 결과 엑셀(CSV) 파일로 저장하기",
                    data=csv_data,
                    file_name=f"요기요_{selected_category.replace('/', '_')}_리스트.csv",
                    mime="text/csv"
                )
            else:
                st.error("화면 이동 및 주소 고정은 완료되었으나 가게 상세 데이터를 추출하지 못했습니다. HTML 구조 점검이 필요합니다.")


if __name__ == "__main__":
    main()