import streamlit as st
import pandas as pd
import numpy as np  # 수학적 로그 함수(np.log1p) 및 통계 계산을 위해 사용
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
import plotly.graph_objects as go  # 통합 추세선을 커스텀 레이어로 추가하기 위해 도입
import io  # 메모리 버퍼 활용을 위한 모듈


def fetch_yogiyo_html(target_address, category_name):
    """
    지정된 주소와 카테고리에 대해 요기요에서 HTML 소스를 가져오는 함수 (멀티스레드 대응)
    ★ 창 크기 축소로 인한 모바일 모드(리스트 멈춤 현상) 방지를 위해 PC 화면 강제 최대화 옵션 적용
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # [중요 보완] 새 창이 뜰 때 모니터 화면 크기로 최대화하여 PC 버전 UI 유지 (모바일 전환 방지)
    chrome_options.add_argument("--start-maximized")

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

        # ---------------------------------------------------------------------
        # 목표치(200개) 기반 스마트 무한 스크롤 연동
        # ---------------------------------------------------------------------
        TARGET_COUNT = 200
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0

        while scroll_attempts < 25:
            current_loaded_stores = driver.find_elements(By.CLASS_NAME, "restaurant-name")
            if len(current_loaded_stores) >= TARGET_COUNT:
                break

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break

            last_height = new_height
            scroll_attempts += 1
        # ---------------------------------------------------------------------

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

    st.markdown("---")
    st.subheader("⚙️ 데이터 정제 방식 선택")

    col_filter, col_input, col_btn = st.columns([2.5, 2, 1.5])

    with col_filter:
        filter_option = st.radio(
            "데이터 정제 옵션:",
            ["리뷰 30개 이하 제외", "정제할 최소 리뷰 수 직접 입력"],
            key="filter_option"
        )

    with col_input:
        if filter_option == "리뷰 30개 이하 제외":
            review_threshold = 30
            st.number_input("제외할 리뷰 수 기준:", value=30, disabled=True, key="threshold_disabled")
        else:
            review_threshold = st.number_input("제외할 리뷰 수 기준:", min_value=0, value=30, step=5, key="threshold_enabled")

        st.caption("⚠️ *입력한 숫자 이하의 리뷰 수의 가게는 통계되지 않습니다.*")

    with col_btn:
        st.write("")
        st.write("")
        start_button = st.button("🚀 통합 크롤링 및 정제 시작", use_container_width=True)

    if start_button:
        if not address_input.strip():
            st.warning("주소를 입력해 주세요.")
            return

        st.info("🔥 멀티스레딩(병렬 처리) 가동! 전체 화면 PC 모드로 3개의 브라우저가 안전하게 크롤링을 시작합니다.")

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

            st.session_state.combined_df = df_result
            st.session_state.has_data = True

    if st.session_state.get("has_data", False):
        df_raw = st.session_state.combined_df.copy()

        # 리뷰 수가 0인 곳은 분석 대상에서 완전히 제외 (결측치 제거)
        df_raw = df_raw[df_raw["리뷰 수"] > 0]

        # 사용자가 지정한 임계값 필터링 적용
        if review_threshold > 0:
            df_display = df_raw[df_raw["리뷰 수"] > review_threshold]
            st.success(f"🎉 데이터 로드 완료! (리뷰 {review_threshold}개 이하 제외 후 총 {len(df_display)}곳의 매장 분석 중)")
        else:
            df_display = df_raw.copy()
            st.success(f"🎉 데이터 로드 완료! (총 {len(df_display)}곳의 매장 분석 중)")

        df_sorted = df_display.sort_values(by=["별점", "리뷰 수"], ascending=False).reset_index(drop=True)
        df_sorted.index = df_sorted.index + 1

        # 1단계. 데이터 수집 결과 표출
        st.subheader("📋 정제 및 필터링 완료된 데이터 테이블")
        st.dataframe(df_sorted, use_container_width=True)

        # 2단계. 산점도 출력
        st.subheader("📊 리뷰 수(자연로그 변환)와 별점의 산점도")

        df_sorted["리뷰 수 (자연로그 변환)"] = np.log1p(df_sorted["리뷰 수"])

        # 추세선 활성화 제어 체크박스
        show_trendline = st.checkbox("🎯 산점도에 통합 추세선 표시하기 (진한 검은색 실선)", value=True)

        # 기본 산점도 빌드
        fig = px.scatter(
            df_sorted,
            x="리뷰 수 (자연로그 변환)",
            y="별점",
            color="카테고리",
            hover_name="가게명",
            labels={"리뷰 수 (자연로그 변환)": "리뷰 수 [자연로그 변환축]", "별점": "평점 (별점)"},
            title="상권 내 업종별 평점 및 리뷰 분포 현황 (통합 회귀 분석선 포함)"
        )

        # 업종 구분 없이 통합된 '진한 검은색 실선' 추세선 최상단 추가 로직
        if show_trendline and len(df_sorted) > 1:
            x_vals = df_sorted["리뷰 수 (자연로그 변환)"]
            y_vals = df_sorted["별점"]

            # 1차 선형회귀 선 기울기 및 절편 계산
            slope, intercept = np.polyfit(x_vals, y_vals, 1)

            # 추세선 범위 지정
            x_trend = np.linspace(x_vals.min(), x_vals.max(), 100)
            y_trend = slope * x_trend + intercept

            # Plotly 차트에 통합 검은색 실선 레이어 추가
            fig.add_trace(
                go.Scatter(
                    x=x_trend,
                    y=y_trend,
                    mode="lines",
                    name="통합 추세선 (전체 업종)",
                    line=dict(color="black", width=4.5),  # 가시성을 위해 두께를 대폭 두껍게 고정
                    hovertemplate="통합 추세선 예측 평점: %{y:.2f}<extra></extra>"
                )
            )

            # 레이아웃 설정을 통해 추세선이 마커(데이터 점) 위로 올라오도록 보정
            fig.update_layout(scattermode="group")

        fig.update_yaxes(range=[0.0, 5.0], tickvals=[0, 1, 2, 3, 4, 5], constrain="domain")

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
            ]),
            selector=dict(mode='markers')
        )

        fig.update_layout(height=650, hovermode="closest", legend_title_text="분류 레이블", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

        # 3단계. 리뷰 수 기준 집단 분할 후 별점 히스토그램 생성
        st.markdown("---")
        st.subheader("📈 리뷰 수 규모별 별점 분포 히스토그램 비교 (구간: 0.5 단위)")

        df_under_30 = df_raw[df_raw["리뷰 수"] <= 30]
        df_over_30 = df_raw[df_raw["리뷰 수"] > 30]

        hist_col1, hist_col2 = st.columns(2)

        with hist_col1:
            st.write(f"**① 리뷰 수 30개 '이하' 매장 분포 (총 {len(df_under_30)}곳)**")
            if not df_under_30.empty:
                fig_hist1 = px.histogram(
                    df_under_30,
                    x="별점",
                    nbins=10,
                    range_x=[0.8, 5.2],
                    labels={"별점": "평점"},
                    color_discrete_sequence=['#FF6F61'],
                    template="plotly_white"
                )
                fig_hist1.update_traces(xbins=dict(start=1.0, end=5.0, size=0.5))
                fig_hist1.update_xaxes(tickvals=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
                st.plotly_chart(fig_hist1, use_container_width=True)
            else:
                st.info("조건에 해당하는 매장이 없습니다.")

        with hist_col2:
            st.write(f"**② 리뷰 수 30개 '초과' 매장 분포 (총 {len(df_over_30)}곳)**")
            if not df_over_30.empty:
                fig_hist2 = px.histogram(
                    df_over_30,
                    x="별점",
                    nbins=10,
                    range_x=[0.8, 5.2],
                    labels={"별점": "평점"},
                    color_discrete_sequence=['#4A90E2'],
                    template="plotly_white"
                )
                fig_hist2.update_traces(xbins=dict(start=1.0, end=5.0, size=0.5))
                fig_hist2.update_xaxes(tickvals=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
                st.plotly_chart(fig_hist2, use_container_width=True)
            else:
                st.info("조건에 해당하는 매장이 없습니다.")

        # 다운로드 레이아웃
        st.markdown("---")
        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            csv_data = df_sorted.drop(columns=["리뷰 수 (자연로그 변환)"]).to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📁 마스터 데이터(CSV) 다운로드",
                data=csv_data,
                file_name="요기요_수집자료_통합마스터.csv",
                mime="text/csv"
            )

        with dl_col2:
            html_buffer = io.StringIO()
            fig.write_html(html_buffer, include_plotlyjs='cdn')
            html_bytes = html_buffer.getvalue().encode('utf-8')
            st.download_button(
                label="📊 상관관계 산점도 그래프(HTML) 다운로드",
                data=html_bytes,
                file_name="요기요_상관관계_산점도.html",
                mime="text/html"
            )

        # 4단계. 최종 통계 분석 결과 표출
        st.subheader("📉 최종 통계 분석 결과 (상관계수 및 결정계수)")

        if len(df_sorted) > 1:
            correlation = df_sorted["리뷰 수 (자연로그 변환)"].corr(df_sorted["별점"])

            x_stat = df_sorted["리뷰 수 (자연로그 변환)"]
            y_stat = df_sorted["별점"]

            slope, intercept = np.polyfit(x_stat, y_stat, 1)
            y_pred = slope * x_stat
            y_true = y_stat

            ss_res = np.sum((y_true - (y_pred + intercept)) ** 2)
            ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

            stat_col1, stat_col2 = st.columns(2)
            with stat_col1:
                st.metric(label="🔗 피어슨 상관계수 (r)", value=f"{correlation:.4f}")
                if abs(correlation) >= 0.7:
                    st.write("💡 **해석:** 두 변인 간에 매우 강한 선형적 상관성이 확인됩니다.")
                elif abs(correlation) >= 0.4:
                    st.write("💡 **해석:** 두 변인 간에 다소 유의미한 선형적 상관성이 확인됩니다.")
                elif abs(correlation) >= 0.1:
                    st.write("💡 **해석:** 두 변인 간에 약한 선형적 상관성이 확인됩니다.")
                else:
                    st.write("💡 **해석:** 두 변인 간에 통계적인 선형 상관관계를 정의하기 어렵습니다.")

            with stat_col2:
                st.metric(label="🎯 결정계수 (R²)", value=f"{r_squared:.4f}")
                st.write(f"💡 **해석:** 리뷰 수 로그값이 평점의 변동성을 약 **{r_squared * 100:.2f}%** 만큼 설명할 수 있습니다.")
        else:
            st.warning("분석 데이터 수가 부족하여 상관분석 결과 산출이 불가능합니다.")


if __name__ == "__main__":
    main()
