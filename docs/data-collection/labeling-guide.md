# 라벨링 가이드 v0.1 (#126)

> 상태: **v0.1 초안 — 팀 승인 전**. 파일럿 20 Window 라벨링 후 불일치 사례를 반영해 v0.2, 본 라벨링 전 v1.0으로 올린다.
> `labelGuideVersion` 값은 이 문서의 버전 문자열(`v0.1`)을 그대로 쓴다. [data-analysis-contract.md](../data-analysis-contract.md)의 초기 제안값 `2.0`과 다르므로 팀 결정 후 하나로 통일한다(아래 §8 결정 안건 5).

이 문서는 평가자에게 배포하는 판단 기준이다. 근거는 [data-collection-spec.md §9](../data-collection-spec.md), [ai-spec.md §5·§7](../ai-spec.md), [v2-contract-decisions.md](../v2-contract-decisions.md), [data-analysis-contract.md](../data-analysis-contract.md)와 회의 문서 「6. 데이터 라벨링 및 정답 품질 관리」다.

## 1. 원칙

- 평가자 **3명이 독립적으로** 판단한다. 라벨링 중 서로 상의하지 않는다.
- 평가자는 **수행 시나리오, AI 예측, BE 최종 상태, 참여자 정보를 보지 않는다**. 도구도 이 정보를 화면에 보내지 않는다.
- 시나리오(목표 유지·합리적 우회·점진적 이탈·명확한 이탈)는 **정답이 아니다**. 이탈하라고 지시받은 세션이어도 실제 페이지를 보고 판단한다.
- 정답은 AI·BE 결과에서 복사하지 않는다.
- 판단마다 **짧은 근거**를 남긴다. 페이지 원문을 그대로 옮겨 쓰지 말고, 이메일·전화번호·URL 같은 식별 정보를 적지 않는다.

## 2. 라벨링 단위

| 단위 | 대상 | 라벨 |
| --- | --- | --- |
| 페이지 관련성 (`PAGE_VISIT`) | 유효 Page Visit 1개 | DIRECT / JUSTIFIED_DETOUR / UNRELATED / UNJUDGEABLE |
| Window 탐색 상태 (`WINDOW`) | 연속한 유효 Page Visit 3개 (size 3, stride 1) | NORMAL / TRANSITION / DRIFT / UNJUDGEABLE |

페이지 라벨과 Window 라벨은 **따로** 판단한다. Window 라벨을 정할 때 자신의 페이지 라벨에서 규칙으로 계산하지 말고, 세 페이지 흐름과 체류시간을 보고 직접 판단한다.

## 3. 평가자에게 보이는 정보

| 정보 | 페이지 라벨링 | Window 라벨링 |
| --- | --- | --- |
| 최초 작업 목표 | 표시 | 표시 |
| 페이지 제목·본문 | 표시 | 세 페이지 모두 표시 |
| 검색어(검색 결과 페이지일 때) | 표시 | 표시 |
| 도메인 | 표시 | 표시 |
| 방문 순서 | 세션 내 순번 | 1→2→3 순서 |
| 이전 방문 문맥 | **같은 세션의 이전 방문 제목·검색어만**(기본값, 결정 안건 1) | 표시하지 않음 |
| 이후 방문 | 숨김 | 숨김 |
| 활성 체류시간 | **숨김** | 페이지별 표시 |
| 시나리오·AI·BE 결과·참여자 | 숨김 | 숨김 |

## 4. 페이지 관련성 라벨

판단 질문: **"이 페이지는 최초 작업 목표를 달성하는 데 필요한 정보인가?"** 체류시간은 보지 않는다. 오래 읽었다고 관련 페이지가 되지 않고, 짧게 봤다고 무관해지지도 않는다.

| 라벨 | 기준 | 예시 (목표: Spring Boot JWT 인증 구현 방법 조사) |
| --- | --- | --- |
| DIRECT | 최초 목표를 직접 수행하는 페이지 | JWT 공식 문서, Spring Security 인증 필터 예제 |
| JUSTIFIED_DETOUR | 주제는 달라도 목표 달성에 필요한 배경·비교·선행 지식으로 설명되는 페이지 | Servlet Filter 개념, HTTP 헤더 구조 설명 |
| UNRELATED | 목표와 관련이 있거나 합리적 우회라는 근거가 없는 페이지 | 게임 뉴스, 여행 정보 |
| UNJUDGEABLE | 본문이 너무 짧거나 내용이 주제를 확인할 수 없을 만큼 불충분한 페이지 | 본문이 메뉴·광고 문구뿐인 페이지 |

경계 사례
- **검색 결과 페이지**: 검색어가 목표를 직접 찾는 검색이면 DIRECT, 배경 지식을 찾는 검색이면 JUSTIFIED_DETOUR, 무관한 검색이면 UNRELATED.
- **DIRECT와 JUSTIFIED_DETOUR가 헷갈릴 때**: 페이지 자체가 목표의 산출물에 바로 들어갈 내용이면 DIRECT, 목표를 이해하기 위한 디딤돌이면 JUSTIFIED_DETOUR.
- **JUSTIFIED_DETOUR와 UNRELATED가 헷갈릴 때**: "이 페이지를 읽은 덕분에 목표를 더 잘 수행할 수 있는가?"를 한 문장으로 설명할 수 있으면 JUSTIFIED_DETOUR, 설명이 억지스러우면 UNRELATED.
- **같은 분야지만 다른 주제**(예: 목표는 JWT인데 페이지는 OAuth 마케팅 기사): 목표 수행에 쓰이는 내용이 없으면 UNRELATED.
- 본문 추출 실패 방문은 이미 유효 Visit에서 빠져 있으므로 라벨링 대상에 나오지 않는다. UNJUDGEABLE은 **내용이 있지만 판단할 근거가 부족한** 경우에만 쓴다.

## 5. Window 탐색 상태 라벨

판단 질문: **"이 세 페이지를 연달아 본 시점에 사용자는 목표에서 이탈했는가?"** 마지막(세 번째) 페이지 시점의 상태를 판단한다.

| 라벨 | 기준 |
| --- | --- |
| NORMAL | 목표와 관련된 탐색이나 합리적 우회가 유지되는 상태. 마지막 페이지가 관련·우회이면 앞에 무관 페이지가 있어도 NORMAL로 본다 |
| TRANSITION | 최근 무관 탐색이 이어지지만 아직 이탈로 확정하기 이른 상태 |
| DRIFT | 무관 탐색이 연속되거나, 무관 페이지에 오래 머물러 목표 이탈로 판단되는 상태 |
| UNJUDGEABLE | 세 페이지 중 판단 근거가 부족한 페이지가 있어 상태를 정할 수 없음 |

참고 — BE 운영 규칙(정답 규칙이 **아니다**): 마지막 페이지가 관련·우회이면 NORMAL, 끝에서 연속한 무관 1개(5분 미만) NORMAL, 연속 무관 2개(모두 5분 미만) TRANSITION, 연속 무관 3개 또는 무관 페이지 중 5분 이상 체류가 있으면 DRIFT. 평가자는 이 표를 참고할 수 있지만 흐름과 체류를 보고 직접 판단한다. 사람의 판단과 규칙이 다른 사례가 BE 규칙 검증의 핵심 자료다.

체류시간 기준: 이번 RAW_ONLY 수집에는 AI Window·stateVersion이 없으므로 Window 라벨은 **Export 시점의 최종 활성 체류시간**으로 판단한다(`referenceStateVersion=null`). 기준 시점(P6)이 확정되면 이 절을 갱신한다(결정 안건 2).

## 6. 판단 근거 작성

- 1~500자, 목표와의 관계를 요약한다.
- 좋은 예: "인증 필터 구현에 필요한 Servlet Filter 개념 설명", "최근 두 페이지가 목표와 무관하지만 체류가 짧음".
- 나쁜 예: 본문 문장 복사, URL·이메일·전화번호 기재, "AI가 무관이라고 함" 같은 예측 참조.

## 7. 합의와 일치도

1. 세 평가자의 독립 라벨(`phase=INDEPENDENT`)과 근거를 모두 보존한다.
2. 2명 이상 같은 라벨이면 다수결 라벨을 합의 후보로 기록한다.
3. 3명이 모두 다르면 공동 검토한다. 근거를 함께 보고 합의 라벨과 합의 메모를 남긴다(`phase=CONSENSUS`, `raterId=null`, 원 투표 ID 참조).
4. 합의가 안 되면 UNJUDGEABLE로 남긴다.
5. Fleiss' κ는 **합의 전** 독립 투표로 페이지와 Window를 따로 계산한다. UNJUDGEABLE을 포함한 4범주 κ와, 세 명 모두 판단 가능했던 표본의 3범주 κ를 표본 수와 함께 보고한다. 분모가 0이면 undefined.
6. AI·BE 성능 평가의 분모에서는 UNJUDGEABLE을 빼고 그 수를 함께 공개한다.

## 8. v0.1에서 결정이 필요한 안건

| # | 안건 | v0.1 기본값 (도구 설정) |
| --- | --- | --- |
| 1 | 페이지 라벨링의 이전 방문 문맥 | 같은 세션 이전 방문의 제목·검색어만 표시. 도구 옵션 `--page-context none|prior` |
| 2 | Window 라벨 기준 시점(P6) | Export 최종 체류시간, `referenceStateVersion=null` |
| 3 | 평가자 제공/비공개 정보 | §3 표 |
| 4 | UNJUDGEABLE 정의 | §4 — 추출 실패는 대상 아님, 내용 부족만 |
| 5 | 가이드 버전 체계 | 회의안 v0.1→v0.2→v1.0. 계약 문서의 `2.0` 제안값과 통일 필요 |
| 6 | 합리적 우회의 "우회 이유 기록" | 기존 수집 데이터에 없음. 라벨링에서는 사용하지 않음 |
| 7 | 파일럿 표본 | Test split이 아닌 목표에서 시나리오별 5 Window, 총 20. 시나리오는 표본 선정에만 쓰고 평가자에게 숨김. 파일럿 데이터는 최종 Test에서 제외 |

## 9. 도구 사용법

라벨링 도구는 [tools/individual-local/labeling.py](../../tools/individual-local/labeling.py)다. 입력은 통합 담당자가 만든 암호화 `training-review` 산출물이며, 원문은 메모리에서만 복호화한다. 라벨 파일에는 ID·라벨·근거만 저장된다.

평가자 (각자 자신의 ID로):

```bash
python tools/individual-local/labeling.py serve review-001.tar.age --sha256 <확인한 SHA-256> --identity <age 개인키> --rater R1 --labels-dir <비공개 폴더> [--pilot] [--page-context prior]
```

출력되는 `http://127.0.0.1:<port>/#<token>` 주소를 Chrome으로 연다. 이 주소의 토큰을 다른 사람과 공유하지 않는다. 라벨은 저장할 때마다 `<비공개 폴더>/labels-R1.jsonl`에 원자적으로 기록된다.

담당자 (세 평가자 파일을 모은 뒤):

```bash
python tools/individual-local/labeling.py report labels-R1.jsonl labels-R2.jsonl labels-R3.jsonl --output report.json
python tools/individual-local/labeling.py consensus labels-R1.jsonl labels-R2.jsonl labels-R3.jsonl [--decisions decisions.jsonl] --output human_labels.jsonl
```

`report`는 κ·분포·다수결 후보·공동 검토 목록을 만든다. `consensus`는 다수결 대상은 자동으로, 3명 불일치 대상은 `decisions.jsonl`(공동 검토 결과: `targetType`, `visitId|windowId`, `label`, `adjudicationNote`)에 있을 때만 CONSENSUS 레코드를 만든다. 결정이 없는 불일치 대상은 출력하지 않고 목록으로 보고한다.

라벨 파일과 리포트는 Git·클라우드 동기화 폴더에 두지 않는다.
