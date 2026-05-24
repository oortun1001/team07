import streamlit as st
import pandas as pd
import plotly.express as px
import os
import re

# 0. 페이지 기본 설정
st.set_page_config(page_title="만능 상관관계 분석 프로그램", layout="wide")

st.title("📊 엑셀 & 이미지 서식 메모장 만능 분석 프로그램")
st.write("CSV 파일뿐만 아니라, 특정 서식('가게명:... | 별점:... | 리뷰수:...')으로 적힌 메모장 파일도 100% 자동 파싱하여 통합 분석합니다.")

# 1. 파일 업로드 섹션
st.subheader("📁 1. 파일 다중 업로드 (CSV 및 요기요 텍스트 서식 지원)")
uploaded_files = st.file_uploader(
    "분석하고자 하는 엑셀(CSV) 또는 메모장(TXT) 파일들을 동시에 업로드해 주세요.",
    type=["csv", "txt"],
    accept_multiple_files=True
)


def parse_custom_txt(content):
    """
    이미지에 보이는 서식을 한 줄씩 추적하여 [가게명, 별점, 리뷰 수] 데이터를 추출하는 함수
    """
    parsed_data = []
    lines = content.split('\n')

    for line in lines:
        if "가게명:" not in line:
            continue

        try:
            # 1. 가게명 추출
            store_name = ""
            name_match = re.search(r"가게명:\s*([^|]+)", line)
            if name_match:
                store_name = name_match.group(1).strip()

            # 2. 별점 추출
            rating = 0.0
            rating_match = re.search(r"별점:\s*([0-9.]+)", line)
            if rating_match:
                rating = float(rating_match.group(1).strip())

            # 3. 리뷰 수 추출
            review_count = 0
            review_match = re.search(r"리뷰\s*수?:\s*([0-9]+)", line)
            if review_match:
                review_count = int(review_match.group(1).strip())

            # 카테고리 자동 유추
            category = "기타"
            if "피자" in store_name or "파스타" in store_name:
                category = "피자/양식"
            elif "치킨" in store_name:
                category = "치킨"
            elif "짜장" in store_name or "짬뽕" in store_name or "중국" in store_name:
                category = "중국집"

            parsed_data.append({
                "가게명": store_name,
                "카테고리": category,
                "별점": rating,
                "리뷰 수": review_count
            })
        except Exception:
            continue

    return pd.DataFrame(parsed_data)


# 파일들이 업로드되었을 때 로직 작동
if uploaded_files:
    all_dfs = []

    for uploaded_file in uploaded_files:
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        temp_df = None

        # A. 엑셀(CSV) 파일 처리
        if file_extension == ".csv":
            try:
                temp_df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
            except Exception:
                try:
                    temp_df = pd.read_csv(uploaded_file, encoding="cp949")
                except Exception as e:
                    st.error(f"'{uploaded_file.name}' (CSV) 인코딩 에러: {e}")
                    continue

            if temp_df is not None:
                # 공백 제거
                temp_df.columns = temp_df.columns.str.strip()

                # 💡 [핵심 수정] CSV 파일의 열 이름이 '상호명'일 경우 '가게명'으로 통합 변경
                if "상호명" in temp_df.columns:
                    temp_df = temp_df.rename(columns={"상호명": "가게명"})

                # '리뷰수' 글자 공백 정돈
                if "리뷰 수" not in temp_df.columns and "리뷰수" in temp_df.columns:
                    temp_df = temp_df.rename(columns={"리뷰수": "리뷰 수"})

        # B. 메모장(TXT) 파일 처리
        elif file_extension == ".txt":
            try:
                content = uploaded_file.getvalue().decode("utf-8-sig")
            except Exception:
                try:
                    content = uploaded_file.getvalue().decode("cp949")
                except Exception as e:
                    st.error(f"'{uploaded_file.name}' (TXT) 읽기 실패: {e}")
                    continue

            if "가게명:" in content and "별점:" in content:
                temp_df = parse_custom_txt(content)
            else:
                first_line = content.split('\n')[0] if '\n' in content else content
                delimiter = "," if "," in first_line else "\t"
                uploaded_file.seek(0)
                try:
                    temp_df = pd.read_csv(uploaded_file, sep=delimiter, encoding="utf-8-sig")
                except Exception:
                    uploaded_file.seek(0)
                    try:
                        temp_df = pd.read_csv(uploaded_file, sep=delimiter, encoding="cp949")
                    except Exception:
                        continue
                if temp_df is not None:
                    temp_df.columns = temp_df.columns.str.strip()
                    if "상호명" in temp_df.columns:
                        temp_df = temp_df.rename(columns={"상호명": "가게명"})
                    if "리뷰 수" not in temp_df.columns and "리뷰수" in temp_df.columns:
                        temp_df = temp_df.rename(columns={"리뷰수": "리뷰 수"})

        if temp_df is not None and not temp_df.empty:
            if "가게명" in temp_df.columns and "리뷰 수" in temp_df.columns and "별점" in temp_df.columns:
                # 시각화와 표 표출을 위해 필요한 핵심 컬럼만 딱 추려서 결합 준비
                cols_to_keep = ["가게명", "별점", "리뷰 수"]
                if "카테고리" in temp_df.columns:
                    cols_to_keep.append("카테고리")
                all_dfs.append(temp_df[cols_to_keep])

    # 데이터 통합 및 시각화
    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)

        # 중복 매장 제거
        df = df.drop_duplicates(subset=["가게명"], keep="first")

        # 별점과 리뷰 수 기준으로 정렬하여 가독성 업그레이드
        df = df.sort_values(by=["별점", "리뷰 수"], ascending=False).reset_index(drop=True)
        df.index = df.index + 1

        # 만약 카테고리가 비어있는 행(CSV 데이터 등)이 있다면 '미분류'로 깔끔하게 채워줌
        if "카테고리" in df.columns:
            df["카테고리"] = df["카테고리"].fillna("미분류")

        # 2. 원본 데이터 보기 섹션
        st.subheader("📋 2. 통합 및 정제된 원본 데이터 보기")
        st.write(f"• 성공적으로 결합된 파일: {len(all_dfs)}개 | 중복 정제 후 최종 매장 수: {len(df)}개")
        st.dataframe(df, use_container_width=True)

        # 3. 그래프 시각화 제어 섹션
        st.subheader("📉 3. 상관관계 산점도 그래프")

        if st.button("산점도 시각화 시작"):
            df["리뷰 수"] = pd.to_numeric(df["리뷰 수"], errors="coerce").fillna(0)
            df["별점"] = pd.to_numeric(df["별점"], errors="coerce").fillna(0.0)

            # Plotly 엔진 규격 설정
            fig = px.scatter(
                df,
                x="리뷰 수",
                y="별점",
                color="카테고리" if "카테고리" in df.columns else None,
                labels={"리뷰 수": "리뷰 수 (개)", "별점": "평점 (별점)"},
                range_x=[0, 7000],  # X축 범위 엄격 차단 (0~7000)
                range_y=[0.0, 5.0],  # Y축 범위 엄격 차단 (0~5)
                title="통합 데이터 기준 리뷰 수와 별점의 상관관계 분포"
            )

            fig.update_layout(
                hovermode="closest",
                legend_title_text="업종/분류",
                template="plotly_white"
            )

            st.plotly_chart(fig, use_container_width=True)
            st.success("🎯 모든 파일의 열 이름을 '가게명'으로 자동 통일하여 깨끗한 산점도를 그려냈습니다!")
    else:
        st.error("분석 가능한 유효한 데이터 파일이 없습니다. 업로드한 파일의 컬럼(상호명/가게명, 별점, 리뷰수)을 확인해 주세요.")