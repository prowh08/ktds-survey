# 🔍Azure 기반 설문조사 AI 에이전트

## OpenAI GPT 모델을 활용한 설문조사 자동 생성 및 통계 분석 MVP 프로젝트

<br>

## 📌 프로젝트 개요 (Overview)

**Azure OpenAI의 GPT 모델**을 활용하여, 사용자의 요구에 맞는 설문조사를 자동으로 생성하고 응답 내용을 분석하는 AI 에이전트입니다.
설문 목적에 맞는 문항을 자동으로 만들고, 수집된 답변의 감정과 선호도 등을 분석하여 비즈니스 의사결정에 필요한 인사이트를 제공하는 것을 목표로 합니다.

<br>

## 📊 기존 설문조사 시스템 (AS-IS)
| 구분       | 기존 방식                                                                                      | 문제점                                                                                              |
|------------|------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| 시스템 구성 | 설문조사 각 기능 3개 서비스로 분리하여 운영<br> 서비스 1) 설문 생성 및 결과 저장<br> 서비스 2) 메시지 전송 및 결과 수집<br> 서비스 3) 설문 결과 통계 제공 | - 문항 수정 시 각 서비스 담당자에게 별도 요청 <br> - 정상 발송 및 결과 확인 위해 3개 시스템 모두 확인 <br>- 설문 내용과 문항 직접 설계해야 하여 초기 작성시 많은 시간 소요<br>- 설문 오타 존재시, 개발팀 소스 수정 및 테스트 재 진행해야 해 추가적인 시간 발생<br>|


<br>

## ✨ 주요 기능 (Features)

-   **AI 기반 설문 자동 생성**: 설문 하고 싶은 키워드 입력시 AI가 적합한 질문과 선택지를 포함한 전체 설문지를 생성합니다.
-   **통계 및 시각화**: 수집된 응답 데이터를 바탕으로 만족도, 감성 분석, 응답 추이 등 핵심 지표를 시각화된 대시보드로 제공합니다.
-   **자동 응답 분석**: Language Studio를 활용하여 주관식 답변에 대한 **분석**을 자동화합니다.(감정분석 등)
-   **설문 버전 관리**: 응답이 시작된 설문을 수정할 경우, 기존 데이터를 보존하기 위해 새로운 버전으로 설문을 생성하여 관리합니다.
-   **유연한 설문 관리**: 설문 문항과 배점 등을 언제든지 변경하고 관리 및 설문 결과를 다운로드 할 수 있습니다.

<br>

## 🔧 기술 스택 (Tech Stack)

| 구분 | 기술 | 주요 역할 |
| :--- | :--- | :--- |
| **AI/ML** | `Azure OpenAI Service (GPT-4o-mini)` | 설문 문항 자동 생성, 주관식 답변 요약 및 평가 |
| | `Azure AI Language (Language Studio)` `analyze_sentiment` `extract_key_phrases` | 주관식 답변 감정 분석, 주관식 답변 핵심구문 추출 |
| **Database**| `Azure PostgreSQL Database` | 설문, 응답 데이터 저장 및 관리 |
| **Frontend** | `Streamlit` | 웹 애플리케이션 UI 및 통계 대시보드 구현 |
| **ETC** | `Azure WebApp`,`BlobStorage`  | 웹 앱 빌드 및 배포 관리, 스토리지 |

<br>

## 🧩 아키텍처 (Workflow)

프로젝트의 전체적인 데이터 및 작업 흐름은 아래와 같습니다.

1.  **설문조사 주제 작성**: 사용자가 설문의 목적과 주제를 입력합니다.
2.  **설문조사 생성 요청**: AI 에이전트에게 설문 생성을 요청합니다.
3.  **설문항목 생성**: Azure OpenAI Service가 주제에 맞는 설문 항목을 생성합니다.
4.  **응답 및 제출**: 응답자가 생성된 설문에 답변을 작성하고 제출합니다.
5.  **데이터 저장**: Azure PostgreSQL에 모든 응답 데이터를 저장합니다.
6.  **결과 분석**: Language Studio가 응답 결과에 대한 감정 분석등 결과 분석을 수행합니다.
7.  **통계 출력**: 분석된 결과가 통계 대시보드 화면에 시각화되어 출력됩니다.

<br>

## 🚀 기대 효과 (Expected Outcomes)

-   **업무 효율성 증대**: 담당자의 설문지 생성 시간을 **1시간에서 10분으로 단축**할 수 있습니다. 
-   **데이터 기반 의사결정**: 고객 반응을 정량적/정성적으로 빠르게 분석하여 **데이터 기반의 마케팅 전략 수립**이 가능합니다.
-   **맞춤형 고객 경험 제공**: 수집된 응답자 특성을 바탕으로 개인화된 맞춤형 설문을 제공할 수 있습니다.

<br>

## ⚠️ 주요 고려사항 (Considerations)

-   **개인정보 보호**: 사용자 답변에 포함될 수 있는 민감 정보 및 개인정보를 필터링하는 기능이 필요합니다.
-   **AI 생성 콘텐츠 검토**: AI가 생성한 설문 문구가 설문의 목적과 정확히 부합하는지 검토하는 절차가 필요합니다.
-   **안전성 확보**: 유해하거나 부적절한 내용의 설문이 생성되지 않도록 필터링 기능이 요구됩니다.


<br>

## ⚠️ 설치 및 환경변수
- **설치 환경**
```
pip install streamlit  
pip install openai  
pip install python-dotenv
pip install pandas
pip install SQLAlchemy
pip install plotly
pip install wordcloud
pip install requests
pip install openpyxl
pip install psycopg2
pip install azure
pip install azure-ai-textanalytics==5.3.0
```

- **환경변수**
  - .env.sample 파일 수정하여 .env 파일 생성
```
# Azure OpenAI
AZURE_ENDPOINT="AZURE_ENDPOINT"
OPENAI_API_KEY="OPENAI_API_KEY"
OPENAI_API_VERSION="OPENAI_API_VERSION"
GPT_DEPLOYMENT_NAME="GPT_DEPLOYMENT_NAME"

# Azure Language Service
AZURE_LNG_ENDPOINT="AZURE_LNG_ENDPOINT"
AZURE_LNG_API_KEY="AZURE_LNG_API_KEY"

# Azure Postgres DB
DB_HOST="DB_HOST"
DB_PORT="DB_PORT"
DB_NAME="DB_NAME"
DB_USER="DB_USER"
DB_PASSWORD="DB_PASSWORD"
```

- **VScode WepApp 배포**
1. 루트 폴더 내 "streamlit.sh"와 ".deployment" 파일 생성
```
# streamlit.sh
pip install streamlit  
pip install openai  
pip install python-dotenv
pip install pandas
pip install SQLAlchemy
pip install plotly
pip install wordcloud
pip install requests
pip install openpyxl
pip install psycopg2
pip install azure
pip install azure-ai-textanalytics==5.3.0

python -m streamlit run main.py --server.port 8000 --server.address 0.0.0.0
```

```
# .deployment
[config]
SCM_DO_BUILD_DURING_DEPLOYMENT=false
```
2. Vscode Extensions > Azure 검색 > install
3. Azure 아이콘 클릭 > MS 로그인 > 테넌트 선택 > app service 리소스 선택 > 우클릭하여 deploy to web app
4. 배포 완료 후 Azure portal > 웹앱 > 구성 > 시작 명령 > **bash /home/site/wwwroot/streamlit.sh** 작성
5. 웹앱 다시 시작 > 잠시 후 **https://user25-webbapp.azurewebsites.net/** 접속
