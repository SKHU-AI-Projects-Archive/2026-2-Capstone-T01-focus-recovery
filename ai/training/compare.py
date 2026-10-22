"""
Embedding-only(A)와 Embedding + Context(B) 학습 리포트 비교.

실행 (ai/ 폴더에서, 두 구성을 같은 데이터로 학습한 뒤):
    python -m training.train
    python -m training.train --use-context
    python -m training.compare

구성 선택은 각 구성에서 선택된 모델의 Validation Macro F1로만 한다.
중첩 Test 결과는 보고용이며 선택에 사용하지 않는다.
"""
import argparse
import json
import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS = AI_DIR / "artifacts"


def load_report(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"[Compare] 리포트가 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(name: str, report: dict) -> dict:
    selected = report["selectedModel"]
    candidate = report["candidates"][selected]
    test = candidate["nested"].get("test", {})
    metadata = report["metadata"]
    return {
        "name": name,
        "model": selected,
        "gamma": report["gamma"],
        "validationMacroF1": candidate["validation"]["macroF1"],
        "testMacroF1": test.get("macroF1"),
        "testDriftRecall": test.get("driftRecall"),
        "nSamples": metadata["nSamples"],
        "dataDir": metadata.get("dataDir"),
        "excluded": len(metadata.get("excludedWindows") or []),
    }


def fmt(value) -> str:
    return "-" if value is None else f"{value:.3f}"


def main():
    parser = argparse.ArgumentParser(description="A/B 학습 리포트 비교")
    parser.add_argument("--a", type=Path, default=ARTIFACTS / "training_report_embedding.json")
    parser.add_argument("--b", type=Path, default=ARTIFACTS / "training_report_context.json")
    args = parser.parse_args()

    rows = [summarize("A (Embedding)", load_report(args.a)), summarize("B (+Context)", load_report(args.b))]

    print(f"{'구성':<15}{'모델':<21}{'γ':>6}{'Val F1':>9}{'Test F1':>9}{'DRIFT Rec':>11}{'Window':>8}{'제외':>6}")
    for r in rows:
        print(
            f"{r['name']:<15}{r['model']:<21}{r['gamma']:>6.2f}{fmt(r['validationMacroF1']):>9}"
            f"{fmt(r['testMacroF1']):>9}{fmt(r['testDriftRecall']):>11}{r['nSamples']:>8}{r['excluded']:>6}"
        )

    a, b = rows
    if a["dataDir"] != b["dataDir"] or a["nSamples"] != b["nSamples"]:
        print("\n[Compare] 경고: 두 리포트의 데이터(경로 또는 Window 수)가 달라 직접 비교할 수 없습니다.")
        sys.exit(1)

    if a["validationMacroF1"] is None or b["validationMacroF1"] is None:
        raise SystemExit("[Compare] Validation 결과가 없는 리포트가 있습니다.")
    # 동점이면 더 단순하고 빠른 A를 선택한다.
    winner = b if b["validationMacroF1"] > a["validationMacroF1"] else a
    print(f"\n[Compare] Validation 기준 선택: {winner['name']}")
    if winner is a:
        print("[Compare] 배포하려면 `python -m training.train`으로 A 분류기를 다시 저장하세요.")
    else:
        print("[Compare] 배포하려면 `python -m training.train --use-context`로 B 분류기를 저장하세요. (Context 결과는 캐시 재사용)")


if __name__ == "__main__":
    main()
