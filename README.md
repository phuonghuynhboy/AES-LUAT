# AES LUẬT

AES LUẬT là bản thử nghiệm trợ lý tra cứu văn bản pháp luật sử dụng RAG. Backend
là một ứng dụng FastAPI đơn khối được điều phối bằng LangGraph; lớp truy xuất kết
hợp BM25 và ChromaDB, còn giao diện được xây dựng bằng React, TypeScript và Vite.

Kết quả chỉ nhằm hỗ trợ tra cứu. Người dùng phải đối chiếu văn bản gốc hoặc tham
khảo người có chuyên môn trước khi áp dụng.

## Phạm vi dữ liệu

Snapshot hiện tại gồm 19 văn bản và 3.974 chunk. Danh mục chi tiết được sinh tại
`backend/evaluation/corpus_inventory.md`. Phạm vi kho dữ liệu không đại diện cho
toàn bộ pháp luật Việt Nam.

## Yêu cầu

- Python 3.11+
- Node.js và npm phù hợp với `frontend/package-lock.json`
- Gemini API key

## Cài đặt backend

Từ thư mục gốc:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\backend[test]"
Copy-Item .env.example .env
```

Điền `GEMINI_API_KEY` trong `.env`. 

## Tạo lại ChromaDB

Lệnh sau xóa collection hiện có và lập chỉ mục lại toàn bộ `data/chunks/*.json`:

```powershell
python -m backend.app.ingestion.ingest_chroma --rebuild
```

Sau khi hoàn tất, số vector phải bằng số chunk. Runtime chỉ bật dense retrieval
khi độ phủ ChromaDB đạt tối thiểu 95%; nếu không, hệ thống cảnh báo và dùng
BM25-only.

## Chạy ứng dụng

Backend:

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, trong cửa sổ PowerShell khác:

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Kiểm tra backend tại `http://127.0.0.1:8000/api/health`.

## Kiểm thử tự động

```powershell
python -m pytest backend/tests
Set-Location frontend
npm test
npm run typecheck
```

## Benchmark

Các bộ dữ liệu có vai trò khác nhau:

- `questions.json`: 90 câu định vị sinh từ corpus;
- `questions_natural_draft.json`: 50 câu hỏi tự nhiên, chưa duyệt bởi chuyên gia;
- `questions_retest.json`: dev/sanity check, không dùng thay kết quả chính thức.

Chạy benchmark chính thức sau khi đã khóa dataset và cấu hình:

```powershell
$env:RUN_RAG_EVALUATION = "1"
python -m pytest backend/tests/evaluation/test_rag_benchmark.py `
  -m evaluation -s `
  --eval-dataset backend/evaluation/questions.json
```

Kết quả nằm trong `backend/evaluation/results/run_<UTC timestamp>/`. Thư mục này
đang bị gitignore; trước khi nộp báo cáo cần lưu có chủ đích bundle của lần chạy
được trích dẫn, gồm `summary.json`, `report.md`, `case_results.csv` và hash của
dataset. Không công bố response nếu chứa dữ liệu nhạy cảm.

## Cấu hình cần ghi cùng kết quả

- `RAG_RETRIEVE_TOP_N`
- `RAG_MAX_CONTEXT_CHARS`
- `RAG_MAX_CHUNK_CHARS`
- tổng số chunk và vector
- tỷ lệ phủ ChromaDB và `dense_enabled`
- model Gemini, dataset SHA-256 và run ID

Không trộn số liệu giữa các lần chạy hoặc giữa benchmark chính thức với sanity
check.
