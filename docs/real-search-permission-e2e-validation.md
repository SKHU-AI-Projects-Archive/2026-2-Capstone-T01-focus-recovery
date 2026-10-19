# 실제 검색·Chrome 사이트 권한 E2E 검증 — Issue #59

검증일: 2026-10-19 (Asia/Seoul). [Issue #59](https://github.com/SKHU-AI-Projects-Archive/2026-2-Capstone-T01-focus-recovery/issues/59)의 전체 본문을 기준으로 한다. **최신 판정은 아래 후속 검증을 따른다. 파일럿 보류: Google BLOCKED, 권한 재허용 후 동일 세션의 방문 전송 FAIL.** 합성 fixture, 모의 Chrome API, manifest 사전 권한은 실제 서비스·수동 승인 성공을 대체하지 않는다. 최초 검증 기록은 실패와 환경 격리 실수를 포함해 뒤에 보존한다.

## #62 병합 후 #59 후속 검증

### 기준 및 변경 범위

- 공식 main `cc01ff483ab16546c9b127296c3ad0bfb301bc8d`에서 PR #62 병합을 확인했다. #61은 OPEN / Draft였다. 기존 #59 브랜치에 공식 main을 merge하여 기존 작업과 이력을 보존했다. 다른 worktree·Fork main·공식 main은 변경하지 않았다.
- #60의 제품 수정·fixture·기본 활성화된 25개 검색 회귀는 main에서 가져왔다. #59에서 별도의 제품 수정은 하지 않았다. 이전 `RUN_KNOWN_SEARCH_BUG` 조건은 제거됐으며, 원래 2개 실패 사례도 기본 실행에서 PASS한다.
- #59 브라우저의 옛 Naver 안전 제외 기대를 **같은 최소 fixture의 정상 추출·organicResultCount=1·기존 방문 보존**으로 갱신했다. main의 빈 결과 제외 검사는 별도로 유지한다.
- 새 권한 결함의 재현 테스트 1개를 `tests/durable-background.test.ts`에 추가했다. 현재 제품에서 **기대 sequence=2 / 실제=1로 실패**한다. SKIP·환경 변수·expected-failure로 숨기지 않았으며 기본 `npm test`가 exit 1임을 명시한다. 이 Draft PR은 바로 병합 가능한 상태가 아니다.

### 실제 Naver 재검증과 합성 회귀의 구분

[#60 보고서](naver-search-dom-fix-validation.md)의 수정 후 실제 Chrome → 실제 Spring Boot → 별도 MySQL 실행 결과를 참조한다. 이 후속 단계에서 실서비스 검색 요청을 반복하지 않았다.

| #59 Naver 체크 항목 | 최신 판정 | 근거·범위 |
| --- | --- | --- |
| 검색어·제목·설명·정규화 URL 보존 | PASS (#60 실서비스 실행) | 영어/한국어 2방문, SQL 필드 길이·해시·visitId/sequence 대조 |
| 검색어 변경·연속 문서 이동 | PASS (관측 2검색) | 영어→한국어, 서로 다른 UUID와 sequence 1,2, 재전송 200 |
| 실제 빈 결과의 안전 제외 | PASS (관측 샘플) | 희소 공개 검증어에서 유효 방문·DB 증가 없음 |
| 블로그·뉴스·외부 결과 클릭 이동 | SKIP | 해당 이동의 종단 저장은 아직 실행하지 않음 |
| 실제 SPA·증분 로딩·A/B 구조 변화 | SKIP | #60은 두 전체 문서 이동을 검증. 합성 MutationObserver 검사를 실제 SPA 성공으로 대체하지 않음 |
| 광고가 실제 표시된 표본의 오수집 여부 | SKIP | #60 실서비스 표본에 명확한 광고가 없었음. 광고·AI·추천 경계의 합성 검사는 PASS |
| Google 체크리스트 전체 | BLOCKED (최초 실제 관측 유지) | 비정상 트래픽/reCAPTCHA로 정상 DOM 접근 불가. 재요청·우회 없음 |

### 실제 Chrome 권한 → BE → DB

새 프로필 2개와 **수집 사이트 사전 권한을 추가하지 않은** 임시 빌드를 사용했다. API의 localhost 필수 권한만 있으며 사이트 권한은 실제 toolbar popup과 Chrome 설정 UI로 변경했다. Chrome API로 허용/철회를 모의하지 않았다. 문서는 개인정보 없는 로컬 합성이므로 실서비스 DOM 성공과 구분한다. Chrome for Testing/OS 버전은 최초 환경과 같다.

새 전용 MySQL `focus-recovery-issue59-followup-20261019-d9ba` (생성 ID `8b00b74070bf…`, issue=59 label), DB 포트 `63536`, 별도 고정 JAR의 BE PID `87803`을 사용했다. `server.port=0`으로 할당된 API `63581`의 기동 로그/datasource를 확인하고 첫 생성 세션이 **이번 DB에 존재함**을 검사한 뒤 진행했다. 최초 실행의 포트 충돌 실수를 반복하지 않았다. API 앞 테스트 proxy는 성공 요청을 이 서버로 전달하며, 아래 503만 명시적인 장애 주입이다.

| #59 권한 시나리오 | 판정 | 실제 UI·IDB·SQL 근거 |
| --- | --- | --- |
| 1. 신규 설치·미허용 | PASS (로컬 샘플) | 수집 origin=false, ACTIVE 세션에서도 방문 0, SQL 0 |
| 2. 사용자가 사이트 허용 | PASS | 실제 승인 sheet의 `127.0.0.1의 데이터를 읽고 변경`과 `허용` 버튼 확인·선택 후 정확한 origin 권한=true |
| 3. 신규 페이지 수집 | PASS | 새 경로로 이동해 새 유효 후보 생성, 앞 방문 POST 201·SQL 1행 |
| 4. 기존 활성 페이지 적용 | PASS | 허용 직후 기존 문서가 valid/방문 1건으로 전환 |
| 5. 실제 거부 후 차단 | PASS (차단) / BLOCKED (안내) | 별도 새 프로필의 실제 `거부` 버튼 선택 후 origin=false·기존/새 경로 방문 0·해당 세션 SQL 0. toolbar popup이 닫혀 거부 안내 텍스트 표시는 확인하지 못함. Escape 취소에서도 권한/방문 0을 별도 확인 |
| 6. ACTIVE 도중 철회 | PASS | Chrome 설정의 자동 액세스 스위치 해제. origin=false, 로컬 session=false |
| 7. 철회 후 추가 수집 차단 | PASS (관측 경로) | 새 경로에서도 방문 0·서버 기존 1행 유지 |
| 기존 데이터·실패 영속 큐 처리 | PASS (ACTIVE) | 철회 전 ACK sequence1 및 장애 주입 503 후 실패 sequence2가 실제 IDB에 존재. 철회 후 후보/POST/PATCH 큐 모두 0, 이미 저장된 서버 1행은 유지 |
| 8. 재허용 후 재개 | **FAIL (종단 저장)** | Chrome UI에서 localhost API 권한과 수집 origin을 각각 복구. 재허용만으로 수집되지 않음은 PASS. 같은 시작 요청을 명시적으로 재개하면 로컬 valid 생성이나 sequence1 재사용 → 실제 BE 409 |
| 9. Chrome 완전 종료·재시작 | PASS (관측 상태 보존) / FAIL (재개 후 저장) | 같은 프로필에서 origin=true 유지, 수집 session=false, 충돌한 sequence1 실패 큐·후속 sequence2 대기 큐 보존, SQL 1행 유지. 정상 재개/종료 전체 성공을 뜻하지 않음 |
| 10. 미허용 사이트 미수집 | PASS (로컬 샘플) | 초기/거부/철회 상태에서 기존·신규 경로 모두 0. 임의의 모든 사이트를 검증한 것은 아님 |
| END_PENDING 도중 실제 UI 철회 | SKIP | 이번 수동 재검증은 일반 ACTIVE 철회. 기존 모의 END_PENDING 보존 검사는 별도 회귀 |

Chrome 설정의 자동 액세스를 끄면 **API localhost 권한도 함께 꺼졌다**. 이를 UI에서 별도로 다시 켠 뒤 수집 origin을 켜고, 실제 API에 도달한 409를 확인했다. 따라서 재허용 실패를 단순 API 호스트 미허용으로 판단하지 않는다. 재허용은 Chrome 설정에서 수행했으므로 두 번째 승인 dialog를 확인했다는 뜻은 아니다.

### 발견 결함: 철회 뒤 동일 세션 재개 시 sequence 재사용

1. 새 세션에서 첫 합성 방문을 확정한다. 실제 POST 201, DB sequence1/서로 다른 방문 ID 정책 확인.
2. 두 번째 방문을 확정할 때 proxy에서 503을 주입한다. 실제 IDB의 sequence2 미전송 원본을 확인한다.
3. Chrome UI로 사이트 접근을 철회한다. 로컬 샘플과 전송 큐가 삭제되지만 서버 sequence1은 남는다.
4. API 호스트와 수집 사이트 권한을 복구하고 같은 목표의 보존된 시작 요청을 재개한다. 같은 서버 sessionId로 돌아온다.
5. 새로운 UUID 방문을 확정하면 **sequence1을 다시 보낸다**. 실제 서버는 `409 VISIT_SEQUENCE_CONFLICT`, IDB는 재시도 불가 실패 상태이며 DB는 기존 1행이다.

원인: `background/index.ts`의 `permissions.onRemoved`가 `suspend()`로 시작 영수증을 보존하면서 `collector.state = emptyState()`로 `nextSequence`를 1로 되돌린다. 이후 `startSession()`은 보존된 ACTIVE 응답으로 같은 세션을 `collector.resume()`한다. 서버 저장 이력과 다음 순서를 복구하지 못한다. 큐 삭제 자체의 개인정보 보호 정책과 서버에 이미 저장된 순서의 무결성을 함께 보장해야 한다. 적절한 제품 수정 정책은 후속 작업에서 정해야 하며, 이번 E2E 브랜치에서 임의로 변경하지 않았다. 사용자의 새 Issue 생성 금지 지시에 따라 별도 Issue는 생성하지 않았다.

```sh
cd fe
# 기본 실행에도 포함된다. 현 제품에서 expected 2 / received 1, exit 1.
npm test -- tests/durable-background.test.ts -t 'keeps the next server sequence'
```

### 후속 실행 결과

| 검사 | 판정 | 결과 |
| --- | --- | --- |
| FE `npm test` | **FAIL** | 27파일, **758 PASS / 1 FAIL / 0 SKIP**. 위 새 sequence 회귀만 실패 |
| Naver 기본 회귀 | PASS | `search-live-dom` 25건, 과거 2개 재현도 PASS. Google/구형 Naver 회귀 유지 |
| `npm run typecheck` / `npm run build` | PASS | 최신 main과 #59 테스트를 함께 검사 |
| MV3 headless / headed | PASS | 정상 Naver fixture + 빈 결과 제외·IDB·방문 보존 회귀. 수동 권한과 별개 |
| 실제 BE·DB 방문 스크립트 | PASS | 7방문/sequence1~7, 단계별 SQL/3Window, 중복 replay·장애·Unicode 경계·Worker 복구 |
| 실제 BE·DB 행동 스크립트 | PASS | 기존 12개 시나리오, PATCH ACK·SQL·중복/stale·재시작/재로드 |
| 실제 BE·DB 종료 스크립트 | PASS | 기존 12개 시나리오, 실제 ENDED/SQL·ACK 게이트·재시작/재로드·POST/PATCH 불일치 보존 |
| #60의 실제 Naver·BE 361개 검사 | PASS (별도 실행 인용) | [#60 보고서](naver-search-dom-fix-validation.md). 이번 후속 단계의 재실행으로 계산하지 않음 |
| Windows Stable·다른 Chrome 버전 | SKIP | 이번 macOS Chrome for Testing 환경 밖 |

파일럿 전에는 **재허용 sequence 충돌 제품 수정**, Google 정상 검색의 실서비스 검증, 권한 거부 안내·실제 END_PENDING 철회, Naver 외부/블로그/뉴스 이동 및 동적 로딩의 미실행 항목을 해결해야 한다. #60의 Naver 누락 자체는 수정·실서비스 재검증됐지만 #59 전체 완료를 뜻하지 않는다. AI 학습·데이터셋 수집은 수행하지 않았다.

후속 검증용 BE PID/실행 경로와 MySQL ID/issue label을 확인한 뒤 직접 만든 BE·컨테이너·익명 볼륨·임시 JAR·Chrome 프로필을 정리했다. 기존 서버/컨테이너는 종료하거나 삭제하지 않았다.

## 최초 검증 기록 (PR #62 병합 전)

아래 판정과 명령은 최초 실행 당시의 기록이다. Naver FAIL·known-bug SKIP 등은 위 후속 결과로 갱신됐으며 현재 실행 방법이나 최신 판정으로 사용하지 않는다.

## Git 기준과 환경

- 시작: 현재 worktree의 detached HEAD `5e49cb3`, 추적·미추적 변경 없음. 다른 worktree는 수정하지 않았다.
- `origin`: 개인 Fork `hyeon-marina/2026-2-Capstone-T01-focus-recovery`, `upstream`: 공식 `SKHU-AI-Projects-Archive/2026-2-Capstone-T01-focus-recovery`.
- 공식 최신 main **`739196cd70ef3f763d2f8af69fba85f102395f45`**를 fetch하고 `test/59/real-search-permission-e2e` 생성. 최종 remote 확인에서도 공식·Fork main이 이 SHA이며 기존 원격 `test/59/*` 및 #59 관련 PR은 없었다.
- PR #57은 12:40:19 KST, #58은 14:59:47 KST에 병합됐다. #55·#56 Issue 전체 본문, 두 PR 전체 설명, 기존 검증 보고서를 확인했다.
- README·프로젝트 계획서·PR template 확인. 적용할 AGENTS.md나 별도 Git 가이드는 발견하지 못했다. 계획서의 develop 통합 설명보다 이번 사용자의 공식 main 대상 PR 지시를 우선한다. main 직접 커밋·다른 작업 브랜치 수정·force push·자동 merge 없음.
- macOS **27.0.1 arm64**, Node **25.9.0**, npm **11.12.1**, Chrome for Testing **151.0.7922.34**, Java **21.0.10**, Spring Boot **4.1.1**, MySQL **8.4.9**.
- `npm ci --offline --no-audit --no-fund`로 기존 lockfile의 의존성을 설치했다. 패키지·lockfile·제품 소스·배포 manifest·명세·BE·AI 코드는 변경하지 않았다.
- 새 전용 DB: `focus-recovery-issue59-e2e-20261019`, 생성 시 컨테이너 ID `4ff869b1dc75…`, label `focus-recovery.issue=59`, 동적 포트 `127.0.0.1:61807`. 최종 전용 BE는 `127.0.0.1:28159`, `e2e` profile과 명시적 datasource로 실행했다. AI 주소는 `http://127.0.0.1:1`; AI 실패는 저장/Window 결과와 별개다.

### 초기 포트 충돌과 무효 실행

최초 BE 실행에 지정한 `18059`가 이미 다른 Java 프로세스에 점유돼 새 서버가 시작하지 못했다. 이를 확인하기 전에 첫 방문 테스트와 최초 수동 검색 프로필에서 해당 기존 API로 **공개 합성 세션/방문 요청이 전달됐다**. 새 DB는 세션·방문 0행이어서 SQL 대조가 실패했고, 이 실행은 전용 DB 통합 결과에서 제외했다. 기존 서비스의 데이터·프로세스·컨테이너는 삭제하거나 정리하지 않았다. 이 초기 실수 때문에 “모든 실행이 처음부터 전용 DB에만 접근했다”고 주장하지 않는다. 개인 계정·인증정보·개인 검색어는 사용하지 않았다.

이후 미사용 포트 `28159`를 확인하고 새 서버의 **Started 로그, datasource `61807`, 리스닝 프로세스**를 확인했다. 별도 새 검색 프로필로 재검증했고, 최종 방문·행동·종료 검증은 모두 이번 DB에서 실행했다. 재실행 시 포트만 믿지 말고 자신이 시작한 서버의 기동 완료와 DB를 확인해야 한다.

## 기존 기능·테스트 분석

| 경로 | 현재 동작과 기존 검증 |
| --- | --- |
| `src/shared/url.ts` | 지원 검색 경로에서 정규화 전에 `q`/`query` 1개를 디코딩. 공백 정리, 500 code point 제한, 중복·빈 값·제어문자 거부. 정규화 URL에서 Query/Fragment 제거, 검색어는 별도 보존. 민감 경로·파라미터·URL 자격증명 제외 |
| `src/content/search.ts` | Google `#search #rso`의 `.MjjYud`/`.g`와 `a h3`; Naver `#main_pack`의 `web/…` 또는 `ugcItem/searchBasic`와 SDS headline/body1. 광고·AI/메뉴·입력·숨김 영역 제외. 미확인 레이아웃을 body로 대체하지 않음 |
| `src/content/index.ts` | 활성 context와 권한이 있어야 capture. MutationObserver·debounce·재시도, 결과 없음 약 8초 후 `unavailable-content`. 이후 DOM 이벤트 복구, 검색 SPA의 URL+본문 변경 판정 |
| `public/manifest.json`, `vite.config.ts` | MV3, `activeTab`, `scripting`, `storage`, `webNavigation`, `alarms`; HTTP(S) 수집 origin은 optional. 빌드만 API host를 필수 부여하며 API host는 수집 대상에서 제외 |
| `src/popup/index.tsx` | 실제 toolbar에서 현재 HTTP(S) origin을 요청. `permissions.request=false`이면 거부 안내, true일 때 `sync-permissions`. 일반 extension 탭을 활성화한 상태는 현재 사이트 허용 절차와 다름 |
| `src/background/index.ts` | 허용 origin에 동적 script 등록·기존 탭 주입. 각 content 메시지의 실제 frame URL/documentId와 권한을 재확인. `onRemoved`는 일반 ACTIVE 세션의 로컬 수집과 POST/PATCH 큐를 비움. **END_PENDING이면 종료 의도·원본·큐를 보존하고 종료 drain을 계속함** |
| `src/api/`, 전송기·durable-state | POST ACK 이후 PATCH, 최종 ACK 이후 END. IDB 원본·재시도 예산·중복 응답·종료 영수증 보존. 서버에 이미 저장된 행은 로컬 철회/삭제로 삭제하지 않음 |
| `tests/` | 기존 25파일·726건: 검색 URL/추출/메시지/SPA, 권한 frame 재검사, API 호스트 분리, in-flight 철회 ACK 무시, END_PENDING 철회 보존, IDB/전송/종료 회귀를 재사용 |
| `scripts/` | MV3, 방문·행동·종료 통합을 재사용. `live-search-check.mjs`는 dist API에 세션을 만들고 임시 manifest로 사이트 권한을 사전 부여하므로 **수동 승인 검증 도구가 아님**. 이번 실서비스 관측은 별도 임시 Chrome 프로필에서 수행 |

[#55 보고서](fe-collection-e2e-validation.md)는 합성 검색·사전 권한 기반의 실제 BE/DB 회귀였다. [#56 보고서](unicode-content-length-validation.md)는 본문 5,000 code point 계약을 수정했지만 실제 검색·권한 dialog는 미완료였다. 이전 PASS를 이번 실행으로 복사하지 않았으며 해당 회귀를 다시 실행했다.

## 실제 서비스 관측

개인 계정에 로그인하지 않은 새 프로필에서 공개 검증어만 사용했다. Chrome의 실제 외부 요청/응답을 사용했으며 Playwright route interception·HTML 교체·접근 제한 우회는 하지 않았다. 전체 HTML·쿠키·인증정보·검색 원문 덤프를 저장하지 않았다. 아래 DOM 수치는 해당 시점의 구조 관측이며 서비스 전반의 고정 건수가 아니다.

### Google

`Spring Boot JWT` 검색 요청이 정상 검색 화면 대신 `/sorry/index`의 비정상 트래픽 안내·reCAPTCHA로 이동했다. 최종 HTTP 200을 검색 성공으로 처리하지 않았다. CAPTCHA는 조작하지 않았고 정상 결과 DOM을 얻으려는 반복 요청도 하지 않았다. 이 최초 프로필의 서버 연결은 위 무효 실행에 해당하므로 BE 저장 근거로 쓰지 않는다.

| #59 §2 체크 항목 | 판정 | 근거·미완료 범위 |
| --- | --- | --- |
| 일반 검색어 추출 | BLOCKED | 정상 결과 페이지 진입 불가 |
| 검색 결과 제목·설명 | BLOCKED | 정상 DOM 미확인 |
| 실제 Query/Fragment 처리·검색어 보존 | BLOCKED | 실제 서비스 추출/저장 미검증. 합성 URL 회귀만 PASS |
| 결과→일반 웹페이지 방문 | BLOCKED | 결과 링크 진입 불가 |
| 검색어 변경·연속 검색 중복/누락 | BLOCKED | 추가 요청으로 제한 우회하지 않음 |
| 동적 콘텐츠·실제 DOM 변경 | BLOCKED | 정상 DOM 없음 |
| 수집 불가능 페이지의 안전 제외/오류 | BLOCKED | 접근 제한 화면 자체는 확인. 해당 화면에서의 신뢰 가능한 확장→DB 검사 미완료; 합성 실패 제외만 별도 PASS |

### Naver

서로 다른 프로필의 관측에서 결과 미추출을 확인한 뒤, 이번 전용 BE에 연결한 별도 임시 프로필로 영어→한국어 검색을 재검증했다. 이 분리 실행은 임시 manifest에 Naver 수집 권한을 사전 부여했으므로 **실서비스 DOM 관측에는 해당하지만 사용자 승인 PASS에는 해당하지 않는다**.

- 영어 `Spring Boot JWT`, 한국어 `스프링 부트 인증`: HTTP 200, `/search.naver` 정상 화면, 실제 일반 웹 결과 제목·설명 표시.
- `#main_pack a[href] [class*="sds-comps-text-type-headline"]`: 영어 18개 / 한국어 22개. AI·추천 영역이 포함될 수 있어 **organicResultCount로 보고하지 않는다**.
- 기존 Naver `web/…` 및 `ugcItem/searchBasic` 컨테이너: 두 검색 모두 0개. 일반 웹 결과의 `a > span.sds-comps-text-type-headline1`과 SDS layout은 있으나 기존 컨테이너 속성이 없었다. AI 브리핑과 `aipickItem`은 수집 대상 근거로 사용하지 않았다.
- 활성 체류 및 결과 대기 후 두 후보 모두 `excluded/unavailable-content`, 유효 방문 **0건**. 허용 권한/ACTIVE 세션이 있는 상태에서도 재현됐다.
- 해당 전용 서버 세션을 `end-session`으로 종료했고 실제 GET 및 MySQL에서 **ENDED / 방문 0행**을 확인했다.

| #59 §3 체크 항목 | 판정 | 근거·미완료 범위 |
| --- | --- | --- |
| 일반 통합검색 검색어 추출 | FAIL (종단 수집) | 검색 URL에는 정확한 공개 검증어가 있으나 결과 미추출로 검색 방문/검색어가 저장되지 않음. URL parser 단독 동작은 합성 재현에서 PASS |
| 제목·설명 추출 | FAIL | 화면에 일반 결과가 있으나 추출기 null, #60 |
| 실제 Query/Fragment 처리·검색어 보존 | FAIL (종단 저장) | 원문 query와 fragment를 가진 두 요청을 사용했으나 저장 방문 0행. 정규화 함수의 합성 재현은 PASS |
| 블로그·뉴스·일반 웹페이지 이동 | BLOCKED | 검색 수집 실패로 연결된 방문 기록을 검증하지 못함. 목적지 방문 자체도 이번 실행에서 수행하지 않음 |
| 검색어 변경·연속 검색 중복/누락 | FAIL | 영어→한국어 실제 문서 이동을 수행했으나 둘 다 0건으로 누락. 정상 수집 후 중복 여부는 미검증 |
| 동적 콘텐츠·실제 DOM 변경 | FAIL / BLOCKED | 현재 컨테이너 차이 FAIL. 실제 SPA·증분 로딩의 정상 수집 성공은 BLOCKED |
| 수집 불가능한 페이지 안전 처리 | PASS (관측 샘플) | unknown 구조를 unavailable-content로 제외, 서버 방문 0. 실제 빈 결과·서비스 오류 화면까지 검증한 것은 아님 |

결함은 [Bug #60](https://github.com/SKHU-AI-Projects-Archive/2026-2-Capstone-T01-focus-recovery/issues/60)으로 분리했다. 제품 selector를 임의 수정하지 않았다.

## 실제 Chrome 권한 검증

수동 UI는 Chrome for Testing의 실제 toolbar → 수집기 → `현재 사이트 수집 허용`으로 접근했다. Naver 및 개인정보 없는 `127.0.0.1` 합성 문서에서 **사이트 데이터를 읽고 변경**하는 실제 승인 dialog와 허용·거부 버튼을 확인했다. 다만 native UI 자동화에서 창/포커스 변경 및 오래된 AX 상태가 발생했고, 거부 버튼 조작 시도 뒤에도 허용 origin이 관측되는 등 버튼 선택과 최종 결과를 안정적으로 대조하지 못했다. 이를 제품 권한 결함이나 거부 성공으로 단정하지 않는다. API 모의 결과로 실제 dialog 결과를 대체하지 않는다.

로컬 합성 문서에서 실제 Chrome 메뉴의 `사이트 데이터를 읽고 변경할 수 있음 → 확장 프로그램을 클릭할 경우`로 변경한 **철회**는 결과를 확인했다. Chrome의 재로드 안내 전에 권한 목록이 비워지고 ACTIVE session=false·visits=0이 됐다. 실제 IDB aggregate에서 후보/POST 큐/PATCH 큐 모두 0, 새로고침 및 `/after-revoke` 이동 뒤에도 visits=0이었다. 철회 직전 유효 로컬 후보는 1개였지만 아직 미확정으로 POST 큐는 비어 있었다. 따라서 **실제 미전송 큐가 있는 상태의 철회**는 이 관측으로 입증하지 않는다. Chrome 메뉴 변경은 API host 권한도 보이지 않게 만들어 재허용 후 전체 API 흐름을 확정하지 못했다.

| 사용자 시나리오 / #59 §4 | 판정 | 실제 관측 및 한계 |
| --- | --- | --- |
| 1. 신규 프로필 설치·초기 미허용 | PASS | 수정하지 않은 수집 권한의 빌드 로드. 최초 origins는 API localhost뿐, 합성 페이지의 초기 방문 0 |
| 2. 사용자 직접 사이트 허용 | BLOCKED (부분 관측) | 실제 dialog와 이후 origin 부여는 관측했으나 허용 버튼→결과의 재현 가능한 대조 미완료 |
| 3. 허용 후 신규 페이지 수집 | BLOCKED | 수동 허용 단계가 확정되지 않아 전체 조합 PASS 아님 |
| 4. 기존 활성 페이지 권한 적용 | BLOCKED (부분 관측) | 요청 조작 후 기존 합성 페이지 유효 후보 1개는 관측. 명시적 허용 단계와 결합한 재검증 필요 |
| 5. 권한 거부 후 차단·안내 | BLOCKED | 실제 거부 선택 결과 및 안내 확인 미완료. Popup 모의 거부 검사는 별도 PASS |
| 6. ACTIVE 도중 철회 | PASS (로컬 합성 문서) | Chrome 실제 사이트 접근 메뉴 변경, 로컬 세션 중지/방문 제거 |
| 7. 철회 후 추가 수집 차단 | PASS (관측 구간) | 권한·IDB 대조 후 새로고침/신규 경로에서 추가 방문 0. 활성 세션도 중지된 결과이며, 세션을 강제로 유지한 격리 검사는 아님 |
| 8. 재허용 후 수집 재개 | BLOCKED | origin 부여만 관측; 시작 영수증 pending 및 API 권한 영향으로 종단 재개 미완료 |
| 9. Chrome 재시작 권한·세션 | BLOCKED (전체 조합) | 사이트 미허용 프로필 재실행에서 자동 수집 없음 관측. 허용·거부·철회를 거친 권한/세션/큐 전체 행렬 미검증. 기존 합성 API 브라우저 복구는 별도 PASS |
| 10. 권한 없는 사이트 미수집 | PASS (초기 샘플) | ACTIVE 세션+새 프로필+미허용 합성 origin에서 후보/방문 0. 다른 임의 사이트까지 일반화하지 않음 |
| 세션 중 변경 일관성·기존 데이터/IDB 처리 | PASS / BLOCKED | 관측 ACTIVE 로컬 삭제 PASS. 재허용 전체 흐름·실제 failed 큐·END_PENDING 철회는 수동 미검증 |

권한 거부는 기존 허용 데이터를 지우는 동작이 아니며 신규 수집 권한을 얻지 않는다. 일반 철회는 전체 로컬 수집/미전송 큐를 지우므로 재허용만으로 삭제 데이터를 복구할 수 없다. 서버에 이미 저장되거나 전송 중 commit된 행은 남을 수 있다. END_PENDING 철회는 원본/큐를 보존하는 예외다. 이는 현재 구현과 모의 회귀의 확인 결과이며, 철회가 서버 기록 삭제나 모든 네트워크 요청 취소를 보장한다는 뜻은 아니다.

## 실제 BE·DB 통합 / #59 §5

방문·행동·종료의 기존 스크립트를 이번 전용 API/DB에서 실행했다. **검색 DOM은 합성, 사이트 권한은 테스트 manifest 사전 부여**다. 따라서 아래 합성 통합 PASS가 실제 검색/수동 권한 요구사항 PASS는 아니다.

| 체크 항목 | 실제 서비스 판정 | 합성 문서 + 실제 BE/DB 회귀 |
| --- | --- | --- |
| 실제 Google·Naver 검색어 수집·서버 저장 | Google BLOCKED / Naver FAIL | 합성 Google 검색어의 정확한 저장·재전송 PASS |
| 검색 URL·제목·본문·검색어 매핑 | Google BLOCKED / Naver FAIL | 원본 DTO·응답·정규화 URL·제목·본문·query 대조 PASS |
| 일반 페이지 visitId·sequence | PASS (합성 문서) | 실제 Chrome의 7방문, sequence 1~7, 같은 URL 재방문 별도 ID |
| 활성 체류·탭 전환 저장 | PASS (합성 문서) | POST/PATCH ACK, behaviorVersion·SQL/멱등·stale/409 검사 |
| 5방문 이상 Window 생성 | PASS (합성 문서) | 매 ACK SQL 수 0,0,0,0,1,2,3; size 5/stride 1; 구성 [1..5]/[2..6]/[3..7] |
| 중복 요청·재전송 무결성 | PASS (합성 문서) | 중복 POST 200, 동일 행/Window; 응답 유실·Worker/브라우저/reload 복구, PATCH applied=false |
| 권한 변경·로딩 실패 불필요 방문 | BLOCKED (실제 전체 조합) | DOM/URL/짧은 문서·오류·권한 mock의 추가 데이터 차단 PASS. 수동 변경과 SQL 결합 미완료 |
| 세션 종료·미전송 복구 | PASS (합성 문서) | POST/PATCH 전 END 금지, END_PENDING·응답 유실·원본 보존·재시작, 실제 SQL ENDED |

최종 DB 점검 시 세션 **48개(ACTIVE 33 / ENDED 15), 방문 88개, Window 18개**였다. 중간 실패 실행과 기존 로컬 stop 테스트의 ACTIVE 세션을 포함하므로 모두 정상 종료했다고 주장하지 않는다. 실제 Naver 검증 세션은 ENDED/0방문으로 별도 대조했다.

## 실행 결과와 추가 테스트

| 실행 | 판정 | 근거 |
| --- | --- | --- |
| `npm test` | PASS + SKIP | **730 PASS / 미수정 결함 2 SKIP**, 26파일 통과·1파일 skip. 기존 726건 보존 + 권한 4건 |
| `npm run typecheck`, `npm run build` | PASS | 타입·production popup/Worker/content 빌드 |
| `RUN_KNOWN_SEARCH_BUG=1 npm test -- tests/search-live-dom.test.ts` | **FAIL (2건)** | #60의 기대 결과 1건에 실제 null. 기본 실행의 SKIP을 PASS로 세지 않음 |
| `npm run test:browser` | PASS (headless) | 실제 MV3, 합성 API/검색/사전 권한. 추가 Naver 구조의 안전 제외·기존 방문 보존·IDB snapshot 부재 확인. native 창 검사는 이 실행에서 SKIP |
| `HEADED=1 npm run test:browser` | PASS | 위 전체 회귀와 실제 native 다중 창 포커스·최소화·복원. 수동 사이트 권한 dialog 결과를 대체하지 않음 |
| `visit-integration-test.mjs` | PASS (최종 전체) | 7방문·Window SQL·중복·장애·삭제 경합·Unicode 7종·실제 400 원본 보존 |
| `behavior-integration-test.mjs` | PASS | 기존 12개 시나리오 전체, 실제 SQL·POST/PATCH·브라우저/Worker/reload |
| `session-end-integration-test.mjs` | PASS | 기존 12개 시나리오 전체, 실제 종료·END_PENDING·409·영수증·보존 |
| Java 21 `./gradlew --offline test bootJar` | PASS | **16 suite / 361건**, 실패·오류·skip 0 |
| Node 구문·`git diff --check` | PASS | 변경 스크립트 구문·공백 확인 |
| Windows 11 Chrome Stable·모바일·Chrome 106 | SKIP | 이번 macOS/CfT 환경 밖. 출시 지원 범위의 완료 주장 없음 |

전용 서버의 첫 방문 회귀는 뒤쪽 `/document/deletion/2`의 load 대기에서 30초 타임아웃으로 FAIL했다. 앞쪽 7방문/SQL 시나리오만 통과했으므로 전체 PASS로 처리하지 않았다. 실서비스/수동 Chrome과 동시 실행을 끝낸 후 **기대값·timeout·제품 로직 변경 없이** 전체를 재실행해 exit 0을 확인했다. 동시 실행이 원인이라고 확정하지 않으며 재발 시 독립 조사한다. 새 테스트 작성 중 fixture 경로와 잘못 구성한 합성 snapshot으로 생긴 테스트 harness 오류는 수정 후 재실행했다. 제품 결함으로 분류하지 않는다.

| 변경 파일 | 목적 |
| --- | --- |
| `fe/tests/fixtures/naver-20261019.html` | 일반 웹 결과의 컨테이너 차이를 최소 합성 구조로 재현. 실제 제목·본문·URL·추적 속성·해시 클래스 제거 |
| `fe/tests/search-live-dom.test.ts` | 영어/한국어 기대 추출을 유지한 #60 재현 2건. opt-in이면 실제 FAIL; 제품 수정 시 조건을 제거해 기본 활성화할 것 |
| `fe/tests/permission-popup.test.ts` | 모의 request 거부 안내·허용 후 sync·오류 원문 비노출 3건. native dialog 테스트 아님 |
| `fe/tests/durable-background.test.ts` | 실패 POST 원본이 있던 큐의 철회 삭제, stale snapshot 거부, 재허용·Worker 재시작 후 미복원 1건 |
| `fe/scripts/browser-test.mjs` | 같은 최소 fixture를 실제 MV3 합성 응답으로 재사용. 안전 제외 PASS와 수집 기능 FAIL을 구분 |
| `fe/README.md`, 이 문서 | 실행 결과·한계·재현·후속 연결 |

## Issue #59 나머지 체크리스트

### §1 기존 구현·테스트 분석

검색어/결과 로직, MV3 권한/요청 흐름, 기존 Vitest/Playwright, #55·#56 결과/미실행 범위, 환경/체크리스트 정리 **5항목 모두 PASS(문서·코드 분석)**. 동작 전체 PASS의 의미가 아니다.

### §6 개인정보·수집 정책

| 항목 | 판정 | 근거·한계 |
| --- | --- | --- |
| 로그인·인증·결제·개인정보 입력 제외 | PASS (합성) | 기존 URL/DOM/메시지·실제 MV3 합성 회귀. 실제 로그인/결제 페이지에는 접근하지 않음 |
| 검색어·본문 제한 유지 | PASS | 제품 코드 무변경, 검색어 500 / 본문 5,000 code points 및 Unicode 실제 DB 회귀 |
| 실제 계정/개인 데이터의 DB 유입 방지·환경 분리 | PASS (최종 전용 실행) / FAIL (초기 격리) | 로그인·개인 검색어 없음. 최초 잘못된 API 접근은 위에 공개하고 최종 전용 실행과 분리 |
| 수집 실패 원본·오류 상태 | PASS (회귀) | non-retryable 원본·실패 상태 보존. unknown 검색 DOM은 snapshot 없음. 철회의 명시적 삭제는 별도 정책 |
| 로그/보고서의 민감 원문 비노출 | PASS (추적 변경물 검토) | 저장소·Issue에는 최소 합성 HTML과 건수/상태만 기록. 브라우저 AX가 표시한 차단 URL/토큰은 문서·fixture·GitHub로 복사하지 않음 |

### §7 자동화 보강

재현 조건 기록, 개인정보 없는 fixture, 단위/브라우저 회귀 보강, DOM 누락·권한 거부·철회 검사, 실서비스/합성 결과 분리, 기존 수집·복구·종료 회귀 **6항목 모두 PASS(검증 자산 작성/실행)**. 단, #60의 기능 결과는 FAIL, native 승인 전체는 BLOCKED다. 이 문서의 예상 실패 2건을 숨기거나 지원 성공으로 바꾸지 않았다.

### §8 문서화

서비스별 판정, Chrome 승인/거부/철회 결과, 브라우저/OS, 누락/중복/정확성, Bug 분리, 파일럿 선결 조건, 재실행/한계 **7항목 모두 PASS(결과 기록)**. 미완료 시나리오가 있다는 사실까지 문서화한 판정이다.

## 재실행과 수동 후속 절차

```sh
# 저장소 루트: 이미 있는 이름이면 중단하고 새 이름을 선택한다.
docker run --detach --name focus-recovery-issue59-NEW \
  --label focus-recovery.issue=59 --publish 127.0.0.1::3306 \
  --env MYSQL_ALLOW_EMPTY_PASSWORD=yes --env MYSQL_DATABASE=focus_recovery mysql:8.4
docker port focus-recovery-issue59-NEW 3306
docker exec focus-recovery-issue59-NEW mysqladmin ping --silent
cd be
JAVA_HOME=/absolute/path/to/Java21 ./gradlew --offline test bootJar
# 별도 터미널에서 위 DB 포트와 미사용 API 포트로 실행한다.
# 기존 application-local/.env 대신 명시적 e2e profile + datasource를 쓴다.
/absolute/path/to/Java21/bin/java -jar build/libs/focus-recovery-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=e2e --server.address=127.0.0.1 --server.port=미사용_API_포트 \
  '--spring.datasource.url=jdbc:mysql://127.0.0.1:새_DB_포트/focus_recovery?serverTimezone=UTC' \
  --spring.datasource.username=root --spring.datasource.password= \
  --spring.jpa.hibernate.ddl-auto=validate --focus-recovery.ai.base-url=http://127.0.0.1:1
```

**새 서버의 Started 로그, PID/포트, 이번 DB의 schema·행 증가를 확인하기 전 테스트를 실행하지 않는다.** 실행 중인 JAR를 재빌드하지 않는다. 브라우저 테스트는 순차 실행한다.

```sh
cd fe
npm ci --no-audit --no-fund
npm test
npm run typecheck
npm run build
export CHROMIUM_PATH='/absolute/path/to/Google Chrome for Testing'
npm run test:browser
HEADED=1 npm run test:browser
export INTEGRATION_API_BASE_URL=http://127.0.0.1:새_API_포트
export INTEGRATION_MYSQL_CONTAINER=focus-recovery-issue59-NEW
node scripts/visit-integration-test.mjs
node scripts/behavior-integration-test.mjs
node scripts/session-end-integration-test.mjs
# 현재 #60의 실제 미해결 기대 실패를 별도로 재현한다(exit 1).
RUN_KNOWN_SEARCH_BUG=1 npm test -- tests/search-live-dom.test.ts
```

수동 권한 후속은 사이트 권한을 추가하지 않은 `VITE_API_BASE_URL=http://localhost:새_API_포트 npm run build`와 새 Chrome 프로필을 사용한다. 먼저 로컬 공개 합성 문서에서 정확히 재현하고, 실서비스는 공개 검증어만 사용한다.

1. API host 외 수집 권한 없음·후보 0을 확인하고 세션을 시작한다.
2. **현재 웹페이지의 toolbar popup**에서 허용 요청 → 실제 dialog의 거부를 선택한다. 거부 안내·권한 부재·기존 활성/새 문서에서 데이터 0을 대조한다.
3. 같은 요청에서 허용을 선택하고, 실제 origin 권한·기존 문서 주입·새 페이지·DB의 동일 visitId/sequence를 대조한다. 한 단계라도 확인하지 못하면 해당 조합은 BLOCKED다.
4. ACTIVE 세션, 저장 ACK가 있는 방문, 실패한 미전송 POST/PATCH가 있는 상태를 각각 준비한다. Chrome UI로 철회하고 권한 목록·새 메시지·실제 IDB·서버 행을 전후 대조한다. 이미 전송한 서버 행은 로컬 철회로 삭제되지 않아야 한다.
5. 재허용만으로 지운 샘플이 부활하지 않는지, 시작 영수증 확인 후 정상 수집이 재개되는지 확인한다. API host의 권한까지 변경했는지도 별도로 확인한다.
6. END_PENDING의 철회는 원본 보존·최종 전송·종료 게이트를 별도 검증한다. 일반 ACTIVE 철회와 같은 삭제 기대를 적용하지 않는다.
7. 동일 프로필 Chrome 완전 종료/재시작 후 권한·중지 세션·큐 복구·자동 수집 금지와 무권한 사이트 미수집을 대조한다.
8. Google/Naver 정상 결과, 연속 검색·뒤/앞·reload·동적 로딩·결과 링크의 블로그/뉴스/외부 이동을 실제로 수행한다. 각 정상 방문의 저장 필드와 중복/누락을 확인한다. CAPTCHA/로그인/차단은 우회하지 말고 BLOCKED로 남긴다.

이번 실행에서 직접 만든 BE(PID 79482) 종료, 위 컨테이너 ID/issue label 확인 후 전용 MySQL·익명 볼륨 제거, 수동/자동 테스트의 임시 Chrome 프로필 정리를 완료했다. 원래 실행 중이던 서버/컨테이너는 정리 대상으로 삼지 않았다. 재실행 때도 직접 만든 리소스만 정리한다.

## 파일럿 전에 해결할 사항

1. **#60 수정 및 실제 Naver 재검증**: 안정적인 일반 결과 경계, 제목/설명, 광고/AI/추천 제외를 함께 검증하고 재현 2건을 기본 테스트로 활성화한다.
2. Google 정상 검색이 허용되는 환경에서 전체 실서비스 체크리스트를 완료한다. 합성 테스트나 HTTP 200 차단 화면으로 대체할 수 없다.
3. 실제 Chrome 권한 거부/허용/재허용·기존 활성 탭·미전송 큐·END_PENDING·재시작 전체를 수동으로 확정한다. 철회가 로컬 데이터 삭제이고 서버 삭제가 아니라는 안내·동의 정책을 팀이 검토한다.
4. 검색 DOM에서 수집된 실제 공개 데이터의 BE/SQL 매핑과 권한 변화에 따른 중복/누락을 확인한다. 이번 합성 7방문/3Window의 PASS로 대신하지 않는다.
5. 지원 환경 Windows 11 Chrome Stable을 검증하고, 일회용 서버의 기동/포트/DB 확인 절차를 지킨다. AI 모델 학습·분류 성능 개선·본격 데이터셋 수집은 수행하지 않았다.

위 FAIL/BLOCKED를 명시한 Draft PR이며 모든 요구사항 완료나 파일럿 준비 완료를 주장하지 않는다.
