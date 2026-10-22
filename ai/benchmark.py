"""
분석 1건의 지연 측정. BE response-timeout(현재 10s) 조정 여부를 판단하기 위해 사용한다.

실행 (ai/ 폴더에서, 학습된 분류기가 있어야 함):
    python benchmark.py                     # ai/data의 모든 Window를 세션 순서대로 분석
    python benchmark.py --limit 10          # 앞 10개 Window만

API 서버와 같은 경로(FocusRecoveryPipeline.analyze)로 Window를 하나씩 분석한다.
Stride 1 순서로 요청이 들어오는 상황을 재현하므로 임베딩 캐시는 서버와 같은 방식으로 동작한다.
Context 사용 구성이면 Context Model 생성 시간이 함께 측정된다.
"""
import argparse
import time
from pathlib import Path

import numpy as np

from pipeline import FocusRecoveryPipeline
from training.dataset import load_dataset

AI_DIR = Path(__file__).resolve().parent


def percentile(values, q) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


def main():
    parser = argparse.ArgumentParser(description="분석 지연 측정")
    parser.add_argument("--data-dir", type=Path, default=AI_DIR / "data")
    parser.add_argument("--limit", type=int, help="측정할 Window 수")
    args = parser.parse_args()

    samples = load_dataset(args.data_dir)[: args.limit]

    started = time.perf_counter()
    pipeline = FocusRecoveryPipeline.from_default()
    pipeline.embedding_model.warm_up()
    if pipeline.context_model is not None:
        pipeline.context_model.warm_up()
    print(f"[Benchmark] 모델 로드 + warm-up: {time.perf_counter() - started:.1f}s")

    first, rest = [], []
    seen_sessions = set()
    for i, sample in enumerate(samples, start=1):
        behavior = sample.behavior_features if pipeline.classifier.use_behavior else None
        t0 = time.perf_counter()
        result = pipeline.analyze(sample.goal_text, sample.visits, behavior)
        elapsed = time.perf_counter() - t0

        is_first = sample.session_id not in seen_sessions
        seen_sessions.add(sample.session_id)
        (first if is_first else rest).append(elapsed)
        print(f"[Benchmark] {i}/{len(samples)} {sample.window_id} {elapsed:.2f}s {result.result}")

    for name, values in (("세션 첫 Window", first), ("이후 Window", rest)):
        if values:
            print(
                f"[Benchmark] {name} ({len(values)}개): p50 {percentile(values, 50):.2f}s / "
                f"p95 {percentile(values, 95):.2f}s / max {max(values):.2f}s"
            )
    print(f"[Benchmark] context={pipeline.context_model is not None}, device={pipeline.embedding_model.device}")


if __name__ == "__main__":
    main()
