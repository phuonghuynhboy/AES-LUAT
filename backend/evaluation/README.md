# Benchmark RAG pháp luật

Thư mục này chứa khung đánh giá có thể tái lập cho bốn nhóm câu hỏi: `single_hop`, `multi_hop`, `out_of_scope` và `temporal_aware`. Bộ test không dùng LLM để tự chấm chính nó.

## 1. Dataset hiện tại và ground truth

`questions.json` hiện được sinh xác định từ `data/chunks/*.json`, gồm 90 câu:

- 46 `single_hop`;
- 28 `multi_hop`;
- 8 `out_of_scope`;
- 8 `temporal_aware`.

Sinh lại dataset sau khi corpus thay đổi:

```powershell
python backend/evaluation/build_questions_from_chunks.py
```

Generator giữ nguyên văn chunk làm `gold_answer`, dùng đúng `provision_id`, ghép hai chunk vật lý cho multi-hop và chỉ lấy amendment chunk có `valid_from` cho temporal-aware. Quá trình này không gọi model.

Trước khi dùng số liệu trong báo cáo chính thức, chuyên gia pháp lý vẫn phải duyệt câu hỏi, đáp án và fact rubric. Trường `reviewed_by` hiện ghi rõ là chưa duyệt. `questions.template.json` được giữ lại nếu muốn biên soạn thủ công một bộ khác.

Một dataset chính thức phải bảo đảm:

1. Có 80–100 câu đã được chuyên gia pháp lý duyệt:
   - 40–50 `single_hop`;
   - 26–32 `multi_hop`;
   - 7–9 `out_of_scope`;
   - 7–9 `temporal_aware`.
2. Tất cả case chính thức đặt `enabled: true`.
3. Chỉ ghi ID vật lý của chunk trong `gold_citation_groups`, tức `provision_id`. Không ghi `provision_key`.

Mỗi phần tử của `gold_citation_groups` là một yêu cầu chứng cứ. Nhiều `provision_id` trong cùng một nhóm nghĩa là các nguồn tương đương được chấp nhận; nhiều nhóm nghĩa là câu trả lời phải bao phủ đủ từng nhóm.

`answer_rubric.required_facts` nên là các mệnh đề nguyên tử. `any_of` dành cho cụm từ hợp lệ; `patterns` dành cho biểu thức chính quy. `forbidden_facts` mô tả thông tin sai hoặc phiên bản pháp luật không đúng thời điểm. Không lấy chính câu trả lời của hệ thống để tạo rubric.

Với `temporal_aware`, ngày trong `as_of_date` cũng phải xuất hiện rõ trong câu hỏi. API hiện tại chỉ truyền trường `question` cho RAG.

## 2. Định nghĩa chỉ tiêu

- **Citation Accuracy**: tỷ lệ câu trong phạm vi có đủ mọi nhóm citation chuẩn, không có citation thừa và không vi phạm ánh xạ `claim.evidence_chunk_ids -> sources[].provision_id`. Nhãn chuyên gia bổ sung kiểm tra citation có thực sự chứa nội dung của claim hay không.
- **Answer Correctness**: tỷ lệ câu đạt status dự kiến, đúng ngữ nghĩa status và đạt ngưỡng fact rubric mà không chứa forbidden fact. Khi có nhãn chuyên gia, nhãn đó thay điểm rubric tự động.
- **Hallucination Rate**: tỷ lệ câu có ít nhất một lỗi như citation không có source, source không tồn tại/không khớp corpus, claim được hỗ trợ nhưng thiếu chứng cứ, claim `unsupported` lại có chứng cứ, forbidden fact hoặc từ chối ngoài phạm vi không an toàn. Với báo cáo chính thức nên nhập thêm nhãn chuyên gia.
- **Out-of-scope Accuracy**: tỷ lệ câu ngoài phạm vi trả về `refusal`, không có supported claim và `sources` rỗng. `retrieved_sources` được phép tồn tại vì đây không phải citation hiển thị.
- **Temporal Accuracy**: câu temporal đồng thời đúng citation, đúng answer và đáp ứng yêu cầu warning đã khai báo.

`answer_token_f1` chỉ là số tham khảo; không thay thế đánh giá ý nghĩa pháp lý.

## 3. Chạy benchmark khi đã sẵn sàng

Từ thư mục gốc repository, trong PowerShell:

```powershell
$env:RUN_RAG_EVALUATION = "1"
python -m pytest backend/tests/evaluation -m evaluation -s `
  --eval-dataset backend/evaluation/questions.json
```

Mặc định test gọi trực tiếp `backend.app.generation.rag_graph.answer_question`. Kết quả nằm trong `backend/evaluation/results/run_<UTC timestamp>/`:

- `responses.json`: response thô, dùng để replay;
- `summary.json`: chỉ số tổng hợp và kiểm tra ngưỡng;
- `case_results.json`: kết quả chi tiết từng câu;
- `case_results.csv`: bảng đưa vào phân tích/báo cáo;
- `human_review_template.csv`: biểu mẫu chuyên gia;
- `report.md`: bảng kết quả có thể đưa vào phụ lục.

`summary.json` và `report.md` kèm tử số/mẫu số và khoảng tin cậy Wilson 95%. `responses.json` lưu SHA-256 của dataset; replay sẽ dừng nếu ground truth đã thay đổi, tránh ghép response của lần chạy cũ với bộ câu hỏi mới.

Để cố định nơi xuất kết quả, thêm `--eval-output-dir <path>`.

## 4. Quy trình chấm chuyên gia và replay

Sau lần chạy thật, điền `answer_correct` và `hallucination_present` cho mọi câu; điền thêm `citation_correct` cho các câu trong phạm vi. Dùng giá trị `true`/`false`, giữ nguyên `case_id`, sau đó chạy lại mà không gọi model:

```powershell
$env:RUN_RAG_EVALUATION = "1"
python -m pytest backend/tests/evaluation/test_rag_benchmark.py -m evaluation -s `
  --eval-dataset backend/evaluation/questions.json `
  --eval-responses backend/evaluation/results/<run>/responses.json `
  --eval-human-review backend/evaluation/results/<run>/human_review_template.csv `
  --eval-output-dir backend/evaluation/results/<run>-reviewed
```

Replay giúp kết quả trong báo cáo không thay đổi do model hoặc mạng. Có thể đặt thêm ngưỡng Answer Correctness bằng `--eval-min-answer-correctness 0.85`. Hai ngưỡng mặc định là Citation Accuracy `0.85` và Hallucination Rate `0.05`.

## 5. Chạy thử có kiểm soát

`--eval-max-cases N` chỉ dùng để smoke test kỹ thuật. Báo cáo chính thức phải chạy toàn bộ dataset và không dùng tùy chọn này. Test bị khóa bằng biến `RUN_RAG_EVALUATION=1` để tránh vô tình gọi API và phát sinh chi phí.

Không commit file chứa kết quả nếu response hoặc câu hỏi có dữ liệu nhạy cảm.
