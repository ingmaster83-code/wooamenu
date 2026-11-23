# 우아메뉴 (wooamenu)

한국관광공사 TourAPI 국문 관광정보 v2(`apis.data.go.kr/B551011/KorService2`, 콘텐츠 유형 39=음식점, 약 1.3만 곳)로 만든 대표메뉴·영업시간 식당 사이트(Python 정적 생성기). https://wooamenu.wooahouse.com

- `scripts/fetch_data.py` — `areaBasedList2`로 목록(이름·주소·좌표), `detailIntro2`(대표메뉴·취급메뉴·영업시간·휴무·주차·포장·카드)로 업소당 1호출 상세를 `data/details/{id//2000}.json.gz`에 누적. 하루 예산 기본 2500호출(TourAPI 일일 한도는 약 3,300호출). 대표메뉴·영업시간이 비면 페이지를 만들지 않는다.
- 지역은 목록의 `addr1`(시도·시군구) 파싱, 메뉴 그룹은 `build_site.py`의 `GROUPS` 키워드 정규식(대표메뉴→상호→취급메뉴 순). 이미지·개요는 미사용(KTO 이미지 라이선스, 중복콘텐츠 방지).
- `scripts/build_site.py` — 식당 상세 `/place/{id}/`, 지역·시군구 허브, 메뉴 그룹·메뉴×지역·메뉴×시군구 허브, 검색 인덱스. `scripts/check_site.py`로 링크·제목 중복·JSON-LD 점검.
- Actions: 매일 KST 05:30 fetch → 데이터 커밋 → 빌드 → 배포. 시크릿 `API_KEY` 필요. 네이버 소유확인 토큰은 `scripts/common.py` `NAVER_TOKEN`.
