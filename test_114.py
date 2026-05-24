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
import concurrent.futures  # 백그라운드에서 동시에 크롬 창을 띄우기 위한 라이브러리


def fetch_yogiyo_html(target_address, category_name):
    """
    검증하셨던 오리지널 브라우저 구동 스크립트 형태를 100% 그대로 유지합니다.
    이 함수가 멀티스레딩에 의해 각각 독립된 메모리 영역에서 깨끗하게 실행됩니다.
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

        # 6. 보내주신 이미지 기반 상단 카테고리 바 순서 정밀 타격 클릭
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


def extract_store_details(html, category_name):
    """
    원본 데이터 파싱 구조를 100% 유지하되,
    통합 엑셀에서 필터링하여 찾아볼 수 있도록 '카테고리' 열 데이터를 추가로 심어줍니다.
    """
    soup = BeautifulSoup(html, "html.parser")
    stores_data = []

    restaurant_items = soup.find_all("table", class_="item") or soup.find_all("div", class_="col-sm-6")

    if not restaurant_items:
        names = [div.get_text().strip() for div in soup.find_all("div", class_="restaurant-name")]
        return [{"가게명": name, "카테고리": category_name, "별점": 0.0, "리뷰 수": 0} for name in names]

    for item in restaurant_items:
        # 1. 가게명 파싱
        name_element = item.find("div", class_="restaurant-name")
        if not name_element:
            continue
        store_name = name_element["title"].strip() if name_element.has_attr(
            "title") else name_element.get_text().strip()

        # 2. 별점 파싱
        star_element = item.find("span", class_="ico-star1")
        if star_element:
            star_text = star_element.get_text().strip()
            rating = re.sub(r'[^0-9.]', '', star_text)
        else:
            rating = "0.0"

        # 3. 리뷰 수 파싱
        review_element = item.find("span", class_="review_num")
        if review_element:
            review_text = review_element.get_text().strip()
            review_count = re.sub(r'[^0-9]', '', review_text)
        else:
            review_count = "0"

        # 매칭 데이터 저장 (카테고리 명 포함)
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
    동시에 창이 열릴 때 요기요 방화벽에 트래픽 공격으로 오해받지 않도록
    카테고리별로 기동 시간에 미세한 간격(시차)을 주는 안전 스레드 워커입니다.
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
    st.title("요기요 3대 업종 통합 병렬 수집기 🚀")
    st.write("각각 따로 돌렸을 때의 완벽한 안정성을 유지하며, 크롬 창 3개를 동시에 띄워 누락 없이 일괄 수집합니다.")

    # 텍스트 입력창 초기값 세팅
    default_address = "부산광역시 금정구 부산대학로63번길 2"
    address_input = st.text_input("데이터를 수집할 대상 주소지 입력:", value=default_address, key="address_input")

    # 💡 [요구사항 반영] 번거롭게 하나씩 고르던 라디오 버튼 UI 완벽하게 제거!

    # 크롤링 시작 버튼 클릭 시 로직 구동
    if st.button("통합 크롤링 시작"):
        if not address_input.strip():
            st.warning("주소를 입력해 주세요.")
            return

        st.info("🔥 멀티스레딩(병렬 처리) 가동! 3개의 클린 브라우저가 동시에 기동됩니다. (약 15~20초 소요)")

        # 동시 병렬 타겟 카테고리 리스트
        categories_to_crawl = ["치킨", "피자/양식", "중국집"]
        all_combined_stores = []

        # 💡 concurrent.futures로 독립적인 크롬 창 3개를 백그라운드에서 동시 실행
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 스레드 풀에 각각의 카테고리 크롤링 작업 등록
            futures = [executor.submit(thread_worker, address_input, cat) for cat in categories_to_crawl]

            # 먼저 완료되는 세션부터 순서대로 결과 받아오기
            for future in concurrent.futures.as_completed(futures):
                try:
                    result_data = future.result()
                    if result_data:
                        all_combined_stores.extend(result_data)
                except Exception as e:
                    st.error(f"데이터 수집 스레드 가동 중 에러 발생: {e}")

        # 3. 통합 결과 처리 및 대시보드 출력
        if all_combined_stores:
            df_result = pd.DataFrame(all_combined_stores)

            # [논의된 중복 제거 반영] 가게명과 카테고리가 동시에 일치할 때만 중복 제거!
            # (치킨집이 피자/양식 탭에도 동시 노출되는 '멀티 입점 매장' 데이터는 유실 없이 완벽하게 보존)
            df_result = df_result.drop_duplicates(subset=["가게명", "카테고리"], keep="first")

            st.success(f"🎉 동시 일괄 수집 성공! 누락 없이 총 {len(df_result)}곳의 매장 정보를 확보했습니다.")

            # [논의된 정렬 구조 반영] 모든 업종 데이터를 모아서 [별점 높은 순 -> 리뷰 많은 순]으로 통합 내림차순 정렬
            df_sorted = df_result.sort_values(by=["별점", "리뷰 수"], ascending=False).reset_index(drop=True)
            df_sorted.index = df_sorted.index + 1  # 엑셀 및 화면 표 번호를 1번부터 이쁘게 정렬

            # 브라우저 UI 화면에 마스터 데이터프레임 노출
            st.dataframe(df_sorted, use_container_width=True)

            # 4. 외부 저장을 위한 단 하나의 마스터 엑셀(CSV) 내보내기 연동
            csv_data = df_sorted.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📁 3대 카테고리 통합 마스터 엑셀(CSV) 다운로드",
                data=csv_data,
                file_name="요기요_3대업종_멀티스레드_통합마스터.csv",
                mime="text/csv"
            )
        else:
            st.error("모든 브라우저 세션에서 가게 상세 데이터를 추출하지 못했습니다. 주소 혹은 요기요 사이트 상태를 점검해 주세요.")


if __name__ == "__main__":
    main()