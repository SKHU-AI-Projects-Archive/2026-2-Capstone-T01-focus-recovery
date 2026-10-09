import os
import torch
from typing import List, Union
from sentence_transformers import SentenceTransformer, util

class LocalSemanticEmbeddingModel:
    """
    AI-001: 최초 작업 목표와 페이지 내용 사이의 의미적 관련성을 계산하는 로컬 임베딩 모델 클래스.
    모델을 지정된 local_dir에 다운로드 및 저장하여 반복적인 네트워크 요청을 방지합니다.
    """
    def __init__(self, model_name: str = "Qwen/Qwen3-Embedding-0.6B", save_dir: str = "./ai/models/saved_models/qwen3-embedding"):
        self.model_name = model_name
        self.save_dir = save_dir
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.model = self._load_or_download_model()

    def _load_or_download_model(self) -> SentenceTransformer:
        # 지정한 디렉토리에 모델 및 토크나이저 저장 유무 확인
        if os.path.exists(self.save_dir) and os.listdir(self.save_dir):
            print(f"[AI-001] 로컬 폴더에서 저장된 임베딩 모델을 로드합니다: {self.save_dir}")
            model = SentenceTransformer(self.save_dir, device=self.device)
        else:
            print(f"[AI-001] 로컬 모델을 찾을 수 없습니다. Hugging Face에서 다운로드 후 {self.save_dir}에 저장합니다...")
            os.makedirs(self.save_dir, exist_ok=True)
            model = SentenceTransformer(self.model_name, device=self.device)
            # 로컬 폴더에 모델 및 토크나이저 파일 저장
            model.save(self.save_dir)
            print(f"[AI-001] 모델 저장이 완료되었습니다: {self.save_dir}")
            
        return model

    def calculate_relevance(self, goal: str, title: str, content: str) -> float:
        """
        최초 작업 목표(goal)와 페이지 Title + Content 간의 의미적 관련성(Semantic Relevance)을 계산합니다.
        
        :param goal: 최초 작업 목표
        :param title: 분석 대상 페이지 제목
        :param content: 분석 대상으로 제한된 페이지 본문 (최대 약 5,000자)
        :return: 코사인 유사도 기반 수치 특징 (semanticRelevance)
        """
        if not goal or not (title or content):
            raise ValueError("[AI-001] 유효한 최초 목표와 페이지 텍스트가 필요합니다.")

        # Title과 Content 결합
        page_text = f"Title: {title}\nContent: {content}"
        
        # 임베딩 벡터 생성
        embeddings = self.model.encode([goal, page_text], convert_to_tensor=True, device=self.device)
        
        # 목표 벡터와 페이지 벡터 간 코사인 유사도 산출
        cosine_sim = util.cos_sim(embeddings[0], embeddings[1]).item()
        
        return cosine_sim


# --- 실행 및 검증 예시 코드 ---
if __name__ == "__main__":
    # 모델 인스턴스화 (첫 실행 시 저장, 두 번째 실행부터는 폴더에서 직접 로드)
    embedding_service = LocalSemanticEmbeddingModel()

    sample_goal = "Spring Boot에서 JWT 인증 구현 방법 조사하기"
    sample_title = "Spring Security + JWT 연동 가이드"
    sample_content = "Spring Boot 환경에서 JWT를 활용한 로그인 및 토큰 검증 필터 설정 과정..."

    relevance_score = embedding_service.calculate_relevance(sample_goal, sample_title, sample_content)
    print(f"\n[계산 결과] semanticRelevance: {relevance_score:.4f}")
    