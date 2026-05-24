import streamlit as st
import pandas as pd
import numpy as np  # 수학적 로그 함수(np.log1p) 적용을 위해 사용
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
import plotly.express as px
import io  # 메모리 버퍼 활용을 위한 모듈


def fetch_yogiyo_html(target_address, category_name):
    """
    지정된 주소와 카테고리에 대해 요기요에서 HTML 소스를 가져오는 함수 (멀티스레드 대응)
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
    수집된 HTML 소스에서 가게명, 평점, 리뷰 수를 정밀 정제하는 함수
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
            # 🌟 오타 수정: 기존 "가GE명" -> "가게명"으로 정상 복구 완료!
            stores_data.append({
                "가게명": store_name,
                "카테고리": category_name,
                "별점": float(rating) if rating else 0.0,
                "리뷰 수": int(review_count) if review_count else 0
            })

    return stores_data


def thread_worker(address, category):
    """
    요기요 서버 IP 차단 페널티 방지를 위한 시차 분산형 워커 스레드
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
    st.title("가게의 리뷰 수와 별점의 상관관계 파악 프로그램")
    st.write("요기요에 등록된 부산대 인근 '치킨', '피자/양식', '중국집' 항목 내 식당의 리뷰 수와 별점에 관한 자료를 수집하여 두 변인 간의 상관관계를 파악하는 프로그램입니다.")

    default_address = "부산광역시 금정구 부산대학로63번길 2"
    address_input = st.text_input("데이터를 수집할 대상 주소지 입력:", value=default_address, key="address_input")

    # 버튼과 선택/해제 가능한 '이상치 제거' 토글 가로 정렬 배치
    col1, col2, col3 = st.columns([1.2, 1.8, 3])

    with col1:
        start_button = st.button("통합 크롤링 시작")
    with col2:
        remove_outliers = st.checkbox("이상치 제거 (리뷰 30개 이하 제외)", value=False)

    # 크롤링 시작 버튼을 누르면 새로운 데이터를 수집하여 세션 스테이트에 박제
    if start_button:
        if not address_input.strip():
            st.warning("주소를 입력해 주세요.")
            return

        st.info("🔥 멀티스레딩(병렬 처리) 가동! 3개의 독립 브라우저가 개별 기동됩니다. (약 15~20초 소요)")

        categories_to_crawl = ["치킨", "피자/양식", "중국집"]
        all_combined_stores = []

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
            df_result = df_result.drop_duplicates(subset=["가게명"], keep="first")

            # 수집 완료된 원본 데이터를 세션에 박제
            st.session_state.combined_df = df_result
            st.session_state.has_data = True

    # 다운로드 버튼 클릭 등으로 재실행되어도 세션에 데이터가 살아있다면 화면을 계속 유지함
    if st.session_state.get("has_data", False):
        df_display = st.session_state.combined_df.copy()

        # 이상치 제거 활성화 여부에 따른 실시간 필터링 분기
        if remove_outliers:
            df_display = df_display[df_display["리뷰 수"] > 30]
            st.success(f"🎉 데이터 로드 및 이상치 제거 완료! (리뷰 30개 이하 제외) 총 {len(df_display)}곳의 매장을 표시 중입니다.")
        else:
            st.success(f"🎉 데이터 로드 완료! (리뷰 30개 이하 포함) 총 {len(df_display)}곳의 매장을 표시 중입니다.")

        df_sorted = df_display.sort_values(by=["별점", "리뷰 수"], ascending=False).reset_index(drop=True)
        df_sorted.index = df_sorted.index + 1

        st.dataframe(df_sorted, use_container_width=True)

        st.subheader("📊 리뷰 수(자연로그 변환)와 별점의 산점도")

        # X축 보정: 리뷰 수 컬럼 전체에 수학적 자연로그 ln(x+1) 일괄 주입
        df_sorted["리뷰 수 (자연로그 변환)"] = np.log1p(df_sorted["리뷰 수"])

        # 산점도 차트 생성
        fig = px.scatter(
            df_sorted,
            x="리뷰 수 (자연로그 변환)",
            y="별점",
            color="카테고리",
            hover_name="가게명",
            labels={"리뷰 수 (자연로그 변환)": "리뷰 수 [자연로그 변환축]", "별점": "평점 (별점)"},
            title="상권 내 업종별 평점 및 리뷰 분포 현황 (X축 로그 스케일링 & 규격 구속 버전)"
        )

        # 평점 축 규격 제한: 5.0 상한선 고정
        fig.update_yaxes(
            range=[0.0, 5.0],
            tickvals=[0, 1, 2, 3, 4, 5],
            constrain="domain"
        )

        # 리뷰 수 축 규격 제한: 최대 10,000개 위치 제한
        max_log_limit = np.log1p(10000)
        fig.update_xaxes(
            type="linear",
            range=[0.0, max_log_limit],
            tickvals=[np.log1p(0), np.log1p(10), np.log1p(50), np.log1p(100), np.log1p(500), np.log1p(1000),
                      np.log1p(5000), np.log1p(10000)],
            ticktext=["0", "10", "50", "100", "500", "1k", "5k", "10k"],
            constrain="domain"
        )

        fig.update_traces(
            customdata=df_sorted["리뷰 수"],
            hovertemplate="<br>".join([
                "가게명: %{hovertext}",
                "리뷰 로그변환 값: %{x:.2f}",
                "실제 리뷰 수: %{customdata}개",
                "별점: %{y:.1f}"
            ])
        )

        fig.update_layout(
            height=650,
            hovermode="closest",
            legend_title_text="업종 분류",
            template="plotly_white"
        )

        # 웹 화면에 차트 노출 유지
        st.plotly_chart(fig, use_container_width=True)

        # 산점도 차트를 독립형 HTML 파일 바이너리로 변환
        html_buffer = io.StringIO()
        fig.write_html(html_buffer, include_plotlyjs='cdn')
        html_bytes = html_buffer.getvalue().encode('utf-8')

        # 다운로드 버튼 레이아웃 배치
        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            csv_data = df_sorted.drop(columns=["리뷰 수 (자연로그 변환)"]).to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📁 중복 없는 통합 마스터 엑셀(CSV) 다운로드",
                data=csv_data,
                file_name="요기요_3대업종_순수매장_통합마스터.csv",
                mime="text/csv"
            )

        with dl_col2:
            st.download_button(
                label="📊 상관관계 산점도 그래프(HTML) 다운로드",
                data=html_bytes,
                file_name="요기요_상관관계_산점도_그래프.html",
                mime="text/html"
            )


if __name__ == "__main__":
    main()