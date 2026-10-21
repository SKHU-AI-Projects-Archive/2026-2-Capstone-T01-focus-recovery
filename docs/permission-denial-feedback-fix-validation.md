# 사이트 권한 미허용 안내 복구 — Issue #74

검증일: 2026-10-21 (Asia/Seoul). [Issue #74](https://github.com/SKHU-AI-Projects-Archive/2026-2-Capstone-T01-focus-recovery/issues/74)는 실제 Chrome 권한 요청 후 toolbar Popup이 닫히면 거부 안내도 사라지는 문제다. [PR #61](https://github.com/SKHU-AI-Projects-Archive/2026-2-Capstone-T01-focus-recovery/pull/61)의 실제 Chrome 관측에서 발견됐다.

## Git 기준과 변경 범위

- 시작 브랜치 `test/59/real-search-permission-e2e`, HEAD `f705bdc`, 미커밋 변경 없음. origin은 개인 Fork, upstream은 공식 저장소다.
- 공식 main **`8104072ff7593c5129f2769a4e4835d49d5406e9`**에서 `fix/74/permission-denial-feedback`을 생성했다. 같은 Issue의 기존 PR/브랜치가 없는지 확인했다. 다른 worktree·main·#59 브랜치는 이 수정 브랜치에서 변경하지 않았다.
- #61의 모의 Chrome API 테스트 설정을 참고하고, 미병합 `permission-popup.test.ts`와 파일 충돌·동일 검사 중복을 피하도록 별도 `permission-feedback-popup.test.ts`에 수명·권한 조회 회귀를 추가했다. #61 전체에 의존하지 않는다.
- 제품 변경은 Popup 한 파일이다. Background/Collector, 콘텐츠 추출, IndexedDB/ACK, 권한 허용·철회 정책, manifest, API 계약, BE 제품 코드, DB 스키마, AI, 의존성은 변경하지 않는다.

## 원인과 수정

기존 `allowSite()`는 `permissions.request=false` 후 React 지역 error에만 안내를 넣는다. 실제 네이티브 창 전환으로 Popup이 종료되면 이 상태가 사라진다. 재진입은 새로운 React mount라 거부 안내가 없다.

- Popup을 열 때 활성 HTTP(S) 탭의 origin만 계산하고 `chrome.permissions.contains`로 **현재 실제 권한**을 읽는다. 이미 허용된 사이트를 이전 거부 상태로 잘못 표시하지 않는다.
- 미허용 상태와 `수집하려면 ‘현재 사이트 수집 허용’을 눌러 주세요.`를 보여준다. 권한을 거부/철회한 사이트는 수집하지 않는다는 설명은 Popup 재생성 뒤에도 보인다.
- 현재 권한의 확인 중 / 확인 불가 / 허용 / 미허용을 구분한다. 지원하지 않는 탭·조회 실패를 거부로 추정하지 않으며, 요청 자체가 실패해도 확인 중 상태에 남지 않는다. 원문 오류는 표시하지 않는다.
- 늦게 끝난 최초 조회가 사용자의 더 최근 허용/거부 결과를 덮지 않도록 세대 번호를 검사한다. unmount된 최초 조회도 무시한다.
- 기존 명시적 버튼만 권한을 요청한다. 열기만 해서는 권한 요청·수집 재개를 하지 않는다. 거부 시 sync-permissions를 보내지 않는 기존 동작을 유지한다.
- 안내용 거부 이력·사이트 주소·검색어·본문을 저장하지 않는다. 새 storage key/DB 필드는 없으며 사이트 주소나 Query도 화면에 출력하지 않는다. 허용 상태 표시는 Chrome 접근 권한이며 실제 수집은 기존 세션·URL·DOM 정책을 계속 따른다.

## 재현 테스트: FAIL → PASS

```sh
cd fe
npm test -- tests/permission-feedback-popup.test.ts -t 'shows current missing permission'
```

수정 전에는 native request를 기다리는 중 unmount하고 거부 응답 후 다시 mount하면 권한 상태 안내가 없어 **FAIL / exit1**이었다. 파일을 독립적으로 정리하기 전 최소 재현 실행이며, 같은 기대값은 유지했다. 필터로 제외된 검사는 성공으로 세지 않는다. 수정 후 PASS이며 기본 전체 실행에도 포함한다.

`permission-feedback-popup.test.ts` 총8개는 거부 후 재진입, 다른 현재 사이트로 재진입, 느린 최초 조회와 실제 허용/거부의 경합 2종, 비HTTP/탭 URL 없음 2종, 조회 실패, 요청 실패를 검사한다. 기존 종료 Popup 5개도 함께 통과했다. 모의 Chrome API의 mount/unmount 검사를 실제 네이티브 창 검증으로 대체하지 않는다.

## 실제 Chrome·BE·MySQL

macOS 27.0.1 arm64 / Chrome for Testing 151.0.7922.34 / Node25.9.0 / npm11.12.1 / Java21.0.10 / Spring Boot4.1.1 / MySQL8.4.9. 최신 main의 BE를 Java21로 새로 bootJar 빌드했다. AI 서버는 실행하지 않았다.

새 일회용 DB `focus-recovery-issue74-20261021-d9ba`, 생성 ID `7d24e98640bd…`, label issue=74, MySQL `127.0.0.1:53131`을 사용했다. 고정 JAR `/tmp/focus74-be-BzY5rA/server.jar`, BE PID18376, 동적 API `127.0.0.1:53153`의 Started/datasource를 확인했다. 각 수동 세션을 생성한 직후 이번 DB의 세션1행을 확인했다.

수집 origin을 사전 부여하지 않은 새 headed 프로필과 개인정보 없는 로컬 문서를 사용했다. API localhost 필수 권한만 있으며 사이트 허용/취소를 Chrome API로 모의하지 않았다. 네이티브 UI는 CUA, SQL·수집 상태 조회는 기존 Playwright/전송 proxy를 사용했다. 성공 전송은 실제 Spring Boot에 전달됐다.

| 실제 시나리오 | 판정·근거 |
| --- | --- |
| 초기 미허용 Popup | PASS — 실제 origin=false, 미허용 상태·재허용 방법 표시, 유효 방문0 |
| 네이티브 거부 버튼 선택 | **BLOCKED (선택 불확실)** — 두 새 프로필에서 거부를 의도한 조작 뒤 실제 origin=true/valid1이었다. 두 번째 조작에는 UI 변경 응답도 있었다. 이를 거부 성공이나 수집 차단 성공으로 세지 않는다. 두 세션은 각각 공개 합성 방문1행/ENDED로 종료 |
| 실제 네이티브 Escape 취소 | PASS — 세 번째 새 프로필의 추가 승인 창을 관측하고 Escape로 취소. origin=false / POPUP context0 / 유효 방문0 / SQL0행 |
| 취소 뒤 toolbar Popup 재진입 | PASS — 실제 새 Popup에 미허용 상태와 재허용 방법 모두 표시. 이어서 새 경로로 이동해도 방문0/SQL0 유지. 이 세션은 ENDED/0행으로 종료 |
| Chrome 완전 종료·같은 프로필 재시작 | PASS — origin=false 유지, 실제 toolbar 재진입에 미허용 안내·허용 방법 다시 표시 |
| 실제 네이티브 재허용 | PASS — 새 세션의 같은 사이트에서 실제 요청 창을 열고 Return으로 승인. origin=true / valid1. 이후 toolbar Popup 재진입에서 허용됨 표시, 이전 미허용 표시는 없음 |
| 재허용 → 실제 BE·SQL·종료 | PASS — POST201 / sequence1 / 방문1행, visitId·정규화 URL·제목·본문 exact match, searchQuery=null, 활성 체류62,296ms, ENDED |

첫 두 번의 선택 불확실 실행은 숨기지 않는다. 실제 거부 버튼 클릭을 수정 후 성공으로 주장하지 않으며, 실제 취소 후의 같은 **권한=false / Popup 닫힘·재생성** 경계에서 수정 효과를 확인했다. 수동 세션4개 모두 ENDED였다. 정상 취소/재허용 검증과 앞 두 실행을 구분한다. 중간 UI 조작의 화면 변경 응답도 수집/SQL 성공으로 대체하지 않았다.

정리 직전 SQL로 수동 세션4개 모두 ENDED, 방문 총3행(불확실 선택 실행2행 + 정상 재허용1행)을 재확인했다. 이번 BE의 PID/JAR 경로와 컨테이너 전체 ID·issue label을 대조해 BE·DB·익명 볼륨·고정 JAR 사본을 정리했다. 새 수동 Chrome 프로필3개도 닫고 제거했다. 기존 서버·컨테이너·브라우저 프로필·운영 데이터는 건드리지 않았다.

## 실행 검사

| 검사 | 결과 |
| --- | --- |
| 수정 전 수명 재현 | FAIL — 안내 없음, exit1 |
| 최종 FE `npm test` | PASS — 27파일 / 783개 / FAIL·SKIP0 |
| `npm run build` (typecheck 포함) | PASS — Popup/Background/content production build |
| Java21 `./gradlew --offline bootJar` | PASS — 최신 main의 BE 빌드, 제품 변경 없음 |
| 실제 방문 회귀 | PASS(exit0) — sequence1–7, 5방문부터 Window0/0/0/0/1/2/3, 중복200·Unicode 상한/400·Worker ACK 복구 |
| 실제 행동 회귀 | PASS(exit0) — 12개 시나리오, POST/PATCH/SQL·stale·예산·Worker/브라우저/확장 재시작 |
| 실제 종료 회귀 | PASS(exit0) — 12개 시나리오, 최종 ACK·ENDED·저장 실패/영수증 복구·불일치 원본 보존 |
| 최종 MV3 | PASS(exit0) — 실제 MV3/합성 API·검색 DOM/큐·ACK·Worker/탐색·종료 회귀. native 다중 창/최소화 분기는 SKIP |
| 실제 native 취소·재진입·재시작·재허용·SQL | 위 명시 범위 PASS; 거부 버튼 선택 자체는 BLOCKED |
| Windows Stable / BE 단위 테스트 신규 실행 / Google·Naver 재검색 | SKIP — 환경 밖 / Popup 수정으로 BE 코드 불변 / 실서비스 검색은 #74 범위 밖 |

## 변경 파일·재실행·한계

- `fe/src/popup/index.tsx`: 현재 사이트 권한 재조회·안내와 오래된 응답 차단.
- `fe/tests/permission-feedback-popup.test.ts`: 수명/현재 권한/실패 회귀 8개.
- 이 보고서와 README 링크.

실제 재현은 새 Chrome 프로필에 수정 빌드를 로드하고, 일반 HTTP(S) 공개 문서에서 toolbar 버튼으로 권한 창을 연 뒤 취소·Popup 재진입을 검사한다. 모의 테스트로 실제 거부 선택을 대체하지 않는다. DB 검증 시 반드시 새 일회용 DB와 본인이 기동한 동적 API 포트를 확인한다. 기본 MV3 및 `visit-integration-test.mjs`, `behavior-integration-test.mjs`, `session-end-integration-test.mjs`는 기존 명령을 그대로 사용한다.

권한 표시는 Popup을 열 때와 해당 Popup의 명시적 요청 결과 시점에 갱신한다. 다른 UI에서 권한을 변경했다면 다시 열어 확인한다. 모든 OS·Chrome 버전의 네이티브 거부 버튼 선택은 추가 검증이 필요하다. #59의 Google CAPTCHA·블로그/뉴스 수집·일반 결과 증분 DOM 등 기존 미완료 항목을 해결했다고 주장하지 않는다.
