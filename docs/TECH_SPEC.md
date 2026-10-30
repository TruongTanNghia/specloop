# SpecLoop – Tài liệu kỹ thuật (bản Markdown cho công cụ lập trình AI)

Chuyển từ TaiLieuKyThuat_SpecLoop.docx v1.0 (25/10/2026). Sơ đồ chỉ có trong bản .docx.


# 1. GIỚI THIỆU

## 1.1. Mục đích tài liệu

Tài liệu này đặc tả thiết kế kỹ thuật của hệ thống **SpecLoop** (tên dự kiến) – hệ thống web sinh đặc tả OpenAPI từ tài liệu REST API bằng mô hình ngôn ngữ lớn (LLM), đánh giá đặc tả, kiểm thử API để thu thập phản hồi thực tế và dùng phản hồi đó để phát hiện, tinh chỉnh các ràng buộc OpenAPI. Tài liệu là căn cứ để: (1) lập trình backend Python FastAPI và frontend ReactJS; (2) thống nhất phạm vi bản MVP; (3) viết chương “Phân tích – thiết kế hệ thống” và “Thực nghiệm” trong báo cáo đề tài nghiên cứu khoa học.

## 1.2. Phạm vi hệ thống

**Trong phạm vi:**

- Nạp tài liệu REST API dạng URL, HTML, Markdown, PDF hoặc văn bản dán trực tiếp; tài liệu bằng tiếng Anh.
- Sinh đặc tả OpenAPI 3.0.3 (YAML/JSON) bằng LLM, mỗi phần tử có trích dẫn bằng chứng từ tài liệu.
- Đánh giá đặc tả: hợp lệ cú pháp, hợp lệ theo chuẩn, lint chất lượng, mức có căn cứ (grounding), so khớp với ground truth.
- Kiểm thử API đang chạy (môi trường sandbox hoặc host được cho phép) để thu thập phản hồi thực tế.
- Phát hiện, phân loại sai lệch ràng buộc; sinh đề xuất chỉnh sửa dạng JSON Patch kèm bằng chứng và độ tin cậy; người dùng duyệt; quản lý phiên bản đặc tả.
- Chạy thực nghiệm hàng loạt và xuất số liệu phục vụ báo cáo khoa học.

**Ngoài phạm vi:** API GraphQL/gRPC/SOAP; suy diễn đặc tả từ mã nguồn; kiểm thử bảo mật chuyên sâu (pentest); kiểm thử tải; tự động vượt cơ chế xác thực phức tạp (OAuth có tương tác người dùng, CAPTCHA).

## 1.3. Thuật ngữ và viết tắt

**Bảng 1. Thuật ngữ sử dụng trong tài liệu**

| Thuật ngữ | Giải thích |
|---|---|
| OAS | OpenAPI Specification – chuẩn mô tả REST API dạng máy đọc được; hệ thống dùng phiên bản 3.0.3. |
| Operation | Một cặp (phương thức HTTP, đường dẫn), ví dụ `GET /books`. |
| Ràng buộc (constraint) | Quy tắc trên dữ liệu vào/ra: bắt buộc, kiểu, định dạng, minimum/maximum, độ dài, pattern, enum, phụ thuộc giữa tham số. |
| IR | Intermediate Representation – biểu diễn trung gian dạng JSON do LLM trích xuất cho từng operation, kèm trích dẫn. |
| Evidence / grounding | Trích dẫn nguyên văn từ tài liệu làm căn cứ cho một phần tử; grounding là mức độ phần tử có căn cứ. |
| Atomic fact | Đơn vị thông tin nhỏ nhất dùng để chấm điểm, ví dụ (GET /books, query, limit, maximum, 100). |
| SUT / Target API | System Under Test – API thực tế được kiểm thử. |
| Probe | Request kiểm thử có chủ đích, thay đổi một yếu tố so với request cơ sở để dò một ràng buộc. |
| Observation | Bản ghi một lần gọi API: request, mã trạng thái, header, body, thời gian, kết quả phân loại. |
| Finding | Sai lệch được phát hiện giữa đặc tả và hành vi thực tế (mã D0–D9). |
| Proposal | Đề xuất chỉnh sửa đặc tả dạng JSON Patch (RFC 6902) gắn với một finding. |
| Conformance rate | Tỷ lệ kiểm tra (check) mà phản hồi API phù hợp với đặc tả. |
| GT | Ground truth – đặc tả/nhãn chuẩn dùng để chấm điểm. |

## 1.4. Tài liệu liên quan

- Thuyết minh đề tài NCKH sinh viên: “Xây dựng hệ thống web sinh đặc tả OpenAPI từ tài liệu REST API bằng mô hình ngôn ngữ lớn và tinh chỉnh ràng buộc dựa trên phản hồi kiểm thử API”.
- OpenAPI Specification 3.0.3 – https://spec.openapis.org/oas/v3.0.3
- RFC 6902 – JavaScript Object Notation (JSON) Patch; RFC 6901 – JSON Pointer; RFC 7807 – Problem Details for HTTP APIs.
- Tài liệu Schemathesis (property-based testing cho OpenAPI) – https://schemathesis.readthedocs.io

# 2. TỔNG QUAN GIẢI PHÁP

## 2.1. Bài toán

**Đầu vào:** tài liệu REST API viết cho con người (thường là trang HTML/Markdown) và – nếu có – địa chỉ một môi trường API đang chạy được phép kiểm thử. **Đầu ra:** đặc tả OpenAPI 3.0.3 hợp lệ, trong đó các ràng buộc đã được kiểm chứng hoặc hiệu chỉnh theo hành vi thực tế, kèm báo cáo đánh giá, danh sách sai lệch và lịch sử thay đổi có bằng chứng.

Trọng tâm kỹ thuật là **ràng buộc**: phần dễ sai nhất khi LLM đọc tài liệu (tài liệu thiếu, mơ hồ, lỗi thời hoặc LLM tự suy diễn), nhưng lại quyết định chất lượng của mọi công cụ dùng đặc tả phía sau (sinh test, mock server, sinh mã client). Hành vi thực tế của API – chấp nhận hay từ chối một giá trị, thông báo lỗi nói gì, phản hồi có cấu trúc thế nào – là bằng chứng khách quan để kiểm chứng ràng buộc.

## 2.2. Vòng lặp khép kín

*Hình 1. Vòng lặp khép kín “Tài liệu → OAS → Đánh giá → Kiểm thử → Phản hồi → Tinh chỉnh” (xem sơ đồ trong bản .docx)*

Hệ thống gồm sáu mô-đun nghiệp vụ (M1–M6) chia thành hai pha. **Pha 1** sinh đặc tả từ tài liệu và đánh giá tĩnh. **Pha 2** dùng đặc tả hiện tại để sinh ca kiểm thử, gọi API thực tế, phân tích phản hồi, phát hiện sai lệch và đề xuất chỉnh sửa. Mỗi lần người dùng chấp nhận đề xuất, hệ thống tạo phiên bản đặc tả mới v(k+1) và lặp lại kiểm thử cho đến khi không còn sai lệch đáng kể (hội tụ) hoặc đạt số vòng tối đa.

## 2.3. Nguyên tắc thiết kế

- **Bằng chứng trước (evidence-first):** mọi phần tử trong đặc tả phải có ít nhất một nguồn bằng chứng – đoạn tài liệu hoặc observation. Phần tử không có căn cứ bị gắn cờ, không âm thầm giữ lại.
- **LLM đề xuất, thực thi kiểm chứng:** giả thuyết ràng buộc do LLM rút ra (từ tài liệu hoặc thông báo lỗi) chỉ trở thành đề xuất sau khi được ít nhất một probe xác nhận.
- **Con người duyệt (human-in-the-loop):** mặc định mọi thay đổi cần người dùng chấp nhận; chế độ tự động chỉ áp dụng cho đề xuất có độ tin cậy vượt ngưỡng cấu hình.
- **An toàn khi kiểm thử:** chỉ gọi host trong danh sách cho phép, giới hạn tốc độ và ngân sách request, mặc định chỉ dùng phương thức đọc với API công khai.
- **Tái lập:** phiên bản đặc tả bất biến, lưu đầy đủ prompt, cấu hình, phiên bản mô hình, seed và vết request/response.
- **Mô-đun hóa:** LLM, chiến lược kiểm thử và luật phát hiện sai lệch là các thành phần cắm thêm (plugin) qua giao diện thống nhất.

## 2.4. Ví dụ minh họa xuyên suốt

Các phần sau dùng chung một ví dụ: API thư viện sách **Bookstore-Lab** do nhóm tự xây dựng để thực nghiệm có kiểm soát. Tài liệu (tiếng Anh) mô tả operation liệt kê sách như sau:

```
GET /v1/books
Returns a paginated list of books.
Query parameters
  limit   integer   Number of books per page. Defaults to 20.
  page    integer   Page number, starting from 1.
  sort    string    Required. Sort field: title | published_at.
  order   string    asc or desc. Only used together with sort.
Response 200: { "items": [Book], "total": integer }
```

Cài đặt thực tế của API khác tài liệu ở ba điểm (được cài cắm có chủ đích): (a) `limit` chỉ nhận giá trị 1–100, vượt ngưỡng trả 400 kèm thông báo “limit must be between 1 and 100”, nhưng tài liệu không nêu; (b) `sort` thực chất không bắt buộc (mặc định `title`); (c) trường `isbn` trong `Book` có thể là `null`. Bảng 2 tóm tắt cách hệ thống xử lý ví dụ này qua từng mô-đun.

**Bảng 2. Ví dụ Bookstore-Lab đi qua vòng lặp**

| Bước | Kết quả |
|---|---|
| M2 – Sinh OAS v0 | `limit`: integer, default 20 (không có min/max); `sort`: required, enum [title, published_at]; `order`: enum [asc, desc]; `x-dependencies`: “IF order THEN sort;”; `isbn`: string. |
| M3 – Đánh giá | Hợp lệ OAS 3.0.3; mọi phần tử có trích dẫn; so với GT hành vi: thiếu 2 ràng buộc của `limit`, sai `required` của `sort`, sai nullable của `isbn`. |
| M4 – Kiểm thử | Probe biên: limit = 40, 80 → 200; 160 → 400; tìm nhị phân → 100 là giá trị lớn nhất được chấp nhận; limit = 0 → 400. Bỏ `sort` → 200 (5/5 lần). 7/40 mẫu phản hồi có `isbn: null`. |
| M5 – Phát hiện | D1 (thiếu minimum = 1, maximum = 100, thông báo lỗi khớp); D4 (sort không bắt buộc – mâu thuẫn tài liệu); D8 (isbn nullable). |
| M6 – Đề xuất | Ba JSON Patch kèm bằng chứng; D1 có độ tin cậy 0,92 (mục 5.5.6); D4 bị gắn nhãn “mâu thuẫn tài liệu – cài đặt”, chờ người dùng chọn chế độ. |
| Phiên bản v1 | Áp dụng đề xuất được chấp nhận; kiểm thử lại: 3 finding đóng, không phát sinh finding mới → hội tụ. |

# 3. YÊU CẦU HỆ THỐNG

## 3.1. Tác nhân

- **Người dùng** (sinh viên, kỹ sư kiểm thử/phát triển): tạo dự án, nạp tài liệu, sinh và duyệt đặc tả, chạy kiểm thử, duyệt đề xuất, xuất kết quả.
- **Quản trị viên:** cấu hình nhà cung cấp LLM, khóa API, danh sách host được phép kiểm thử, hạn mức mặc định.
- **Hệ thống ngoài:** dịch vụ LLM (thương mại qua API hoặc mô hình mở chạy cục bộ) và API cần kiểm thử (SUT).

## 3.2. Yêu cầu chức năng

**Bảng 3. Yêu cầu chức năng (MVP: bắt buộc ở bản đầu; MR: mở rộng)**

| Mã | Chức năng | Mô tả | Mức |
|---|---|---|---|
| FR-01 | Quản lý dự án | Tạo/sửa/xóa dự án; cấu hình base URL, kiểu xác thực, host được phép. | MVP |
| FR-02 | Nạp tài liệu | Từ URL (một trang), upload HTML/MD/PDF/TXT hoặc dán văn bản. Crawl nhiều trang: MR. | MVP |
| FR-03 | Phân đoạn | Tự động phân đoạn theo operation; xem, gộp, tách, sửa phân đoạn. | MVP |
| FR-04 | Sinh OAS | Chọn mô hình và tham số; sinh IR có trích dẫn; lắp ráp OAS 3.0.3; vòng tự sửa lỗi. | MVP |
| FR-05 | Xem/sửa OAS | Trình soạn YAML (Monaco), xem trước Swagger UI, bấm phần tử để làm nổi bật trích dẫn. | MVP |
| FR-06 | Kiểm tra hợp lệ & lint | Parse, validate OAS 3.0.3, bộ luật lint chất lượng. | MVP |
| FR-07 | Đánh giá với GT | Upload OAS chuẩn; tính P/R/F1 theo nhóm thành phần, hallucination, omission. | MVP |
| FR-08 | Cấu hình kiểm thử | Base URL, xác thực, phương thức cho phép, ngân sách request, tốc độ, timeout, seed. | MVP |
| FR-09 | Chạy kiểm thử | Schemathesis + probe ràng buộc; tiến trình thời gian thực; hủy giữa chừng. | MVP |
| FR-10 | Xem vết | Bảng observation có lọc theo operation, chiến lược, kết quả; xem chi tiết request/response. | MVP |
| FR-11 | Phát hiện sai lệch | Phân loại D0–D9, gom nhóm theo operation và vị trí JSON Pointer. | MVP |
| FR-12 | Sinh đề xuất | JSON Patch kèm bằng chứng (tài liệu + runtime) và độ tin cậy. | MVP |
| FR-13 | Duyệt đề xuất | Chấp nhận/từ chối/sửa; áp dụng tạo phiên bản mới; kiểm thử hồi quy. | MVP |
| FR-14 | Vòng lặp tự động | Chạy K vòng, tự chấp nhận đề xuất có độ tin cậy ≥ ngưỡng. | MR |
| FR-15 | Phiên bản & diff | Lịch sử phiên bản, so sánh hai phiên bản (YAML diff và diff ngữ nghĩa). | MVP |
| FR-16 | Xuất kết quả | Xuất OAS YAML/JSON (tùy chọn bỏ `x-*`); xuất báo cáo đánh giá CSV/HTML. | MVP |
| FR-17 | Thực nghiệm | Chạy ma trận cấu hình hàng loạt, tổng hợp chỉ số, biểu đồ, xuất CSV. | MR* |
| FR-18 | Tài khoản | Đăng nhập, phân quyền đơn giản (quản trị/người dùng). | MR |

(*) FR-17 không cần cho người dùng cuối nhưng cần cho phần thực nghiệm của đề tài; có thể thực hiện bằng script dòng lệnh dùng chung lớp dịch vụ nếu thiếu thời gian làm giao diện.

## 3.3. Yêu cầu phi chức năng

**Bảng 4. Yêu cầu phi chức năng**

| Mã | Nhóm | Yêu cầu |
|---|---|---|
| NFR-01 | Hiệu năng | Tác vụ dài (sinh OAS, kiểm thử) chạy nền, không chặn giao diện; tiến trình cập nhật ≤ 2 giây/lần qua SSE. Các API đọc dữ liệu thông thường phản hồi < 500 ms. |
| NFR-02 | An toàn kiểm thử | Chỉ gọi host trong danh sách cho phép; chặn dải IP nội bộ (chống SSRF) trừ mạng sandbox; giới hạn tốc độ, ngân sách request, timeout; mặc định chỉ GET/HEAD với API công khai. |
| NFR-03 | Bảo mật | Khóa API, token được mã hóa khi lưu; không ghi log và không gửi cho LLM; header xác thực được che (redact) trong vết. |
| NFR-04 | Tái lập | Phiên bản đặc tả bất biến; lưu prompt, mô hình, tham số, seed; có thể chạy lại một thực nghiệm từ manifest. |
| NFR-05 | Mở rộng | Thêm nhà cung cấp LLM, chiến lược kiểm thử, luật phát hiện mới bằng cách cài đặt giao diện (interface) có sẵn, không sửa lõi. |
| NFR-06 | Khả dụng | Giao diện tiếng Việt, thao tác chính ≤ 3 bước từ trang dự án; hiển thị tốt trên màn hình ≥ 1366 px. |
| NFR-07 | Triển khai | Khởi chạy toàn bộ bằng một lệnh `docker compose up`; cấu hình qua biến môi trường. |
| NFR-08 | Chất lượng mã | Backend có kiểm thử đơn vị cho các thuật toán lõi (phân đoạn, lắp ráp, so khớp, dò biên); lint bằng ruff/ESLint. |

# 4. KIẾN TRÚC TỔNG THỂ

## 4.1. Sơ đồ kiến trúc

*Hình 2. Kiến trúc tổng thể của hệ thống (xem sơ đồ trong bản .docx)*

Hệ thống theo kiến trúc **client – server** ba lớp. Frontend ReactJS là ứng dụng một trang (SPA) giao tiếp với backend qua REST JSON và Server-Sent Events (SSE). Backend FastAPI chỉ đảm nhận xác thực đầu vào, điều phối và truy vấn; mọi tác vụ dài (sinh OAS, đánh giá, kiểm thử, tinh chỉnh) được đẩy vào hàng đợi Redis và do **worker** (Arq) thực thi. Lớp dịch vụ Python dùng chung cho cả API và worker nên logic nghiệp vụ không bị lặp. **LLM Gateway** là điểm duy nhất gọi LLM: chuẩn hóa giao diện giữa các nhà cung cấp, cache theo khóa (mô hình, hash prompt), đếm token và ghi log chi phí.

## 4.2. Công nghệ sử dụng

**Bảng 5. Ngăn xếp công nghệ**

| Lớp | Công nghệ | Vai trò |
|---|---|---|
| Frontend | ReactJS + TypeScript, Vite | Ứng dụng SPA, build nhanh. |
|  | React Router, TanStack Query, Zustand | Định tuyến; quản lý dữ liệu từ server (cache, refetch); trạng thái giao diện. |
|  | Ant Design | Bộ thành phần UI (bảng, form, drawer, tabs). |
|  | @monaco-editor/react, swagger-ui-react, Recharts | Soạn/so sánh YAML; xem trước đặc tả; biểu đồ đánh giá. |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 | REST API, kiểm tra dữ liệu, tự sinh OpenAPI của chính backend. |
|  | SQLAlchemy 2 (async), Alembic | ORM và migration cơ sở dữ liệu. |
| Hàng đợi | Redis + Arq | Hàng đợi tác vụ bất đồng bộ; pub/sub sự kiện tiến trình. |
| CSDL | PostgreSQL (SQLite khi phát triển) | Lưu dự án, phiên bản (JSONB), vết, finding, đề xuất. |
| LLM | Adapter: OpenAI-compatible, Google Gemini, Ollama | Gọi LLM thương mại hoặc mô hình mở cục bộ (ví dụ Qwen2.5-7B-Instruct); structured output theo JSON Schema. |
| Xử lý tài liệu | httpx, trafilatura, BeautifulSoup4, markdownify, PyMuPDF, tiktoken | Tải trang, trích nội dung chính, chuyển Markdown, đọc PDF, đếm token. |
| OAS | ruamel.yaml, openapi-spec-validator, jsonschema | Đọc/ghi YAML giữ thứ tự; kiểm tra hợp lệ OAS 3.0.3; kiểm tra dữ liệu theo schema. |
| Kiểm thử API | Schemathesis (Python API), httpx | Sinh test property-based theo đặc tả; gửi probe tùy biến. |
| Phân tích | genson, jsonpatch, rapidfuzz, deepdiff | Suy diễn schema phản hồi; áp dụng JSON Patch; so khớp trích dẫn; diff ngữ nghĩa. |
| Thực nghiệm | pandas, numpy, scipy, matplotlib | Tổng hợp chỉ số, kiểm định Wilcoxon, bootstrap, vẽ hình cho báo cáo. |
| DevOps | Docker, Docker Compose, Nginx, pytest, Vitest, Playwright | Đóng gói, triển khai, kiểm thử tự động. |

## 4.3. Cấu trúc mã nguồn

Kho mã dạng monorepo gồm hai ứng dụng và thư mục dữ liệu thực nghiệm:

```
specloop/
├── backend/
│   ├── app/
│   │   ├── main.py                 # khởi tạo FastAPI, CORS, router
│   │   ├── core/                   # config, security (mã hóa secret), logging
│   │   ├── db/                     # models SQLAlchemy, session, migrations (alembic)
│   │   ├── schemas/                # Pydantic: request/response, IR, proposal
│   │   ├── api/v1/                 # routers: projects, documents, specs, evaluations,
│   │   │                           #          test_runs, findings, proposals, jobs, experiments
│   │   ├── services/
│   │   │   ├── ingestion/          # fetcher, cleaner, segmenter
│   │   │   ├── generation/         # prompts, extractor (LLM→IR), assembler (IR→OAS), repair
│   │   │   ├── evaluation/         # validator, linter, grounding, fact_matcher, metrics
│   │   │   ├── testing/            # runner, strategies/ (schemathesis, probes), safety, tracer
│   │   │   ├── analysis/           # classifier, boundary_search, msg_miner, schema_infer,
│   │   │   │                       # confidence, proposal_builder
│   │   │   ├── versioning/         # apply_patch, diff, export
│   │   │   └── llm/                # gateway, providers/ (openai, gemini, ollama), cache
│   │   └── worker/                 # Arq settings, job handlers, progress publisher
│   └── tests/                      # pytest: unit + integration (Bookstore-Lab)
├── frontend/
│   └── src/
│       ├── api/                    # client sinh tự động từ /openapi.json của backend
│       ├── pages/                  # Dashboard, ProjectDetail, SpecViewer, TestRun, Findings...
│       ├── components/             # YamlEditor, DiffView, EvidencePanel, TraceTable...
│       ├── hooks/                  # useJobEvents (SSE), useSpec, useProposals...
│       └── store/                  # Zustand: UI state
├── sut/                            # API thực nghiệm: bookstore-lab (FastAPI) + docker files
├── experiments/                    # manifest cấu hình, script chạy hàng loạt, notebook phân tích
└── docker-compose.yml
```

## 4.4. Xử lý bất đồng bộ và cập nhật thời gian thực

Mỗi tác vụ dài là một **job** với vòng đời `queued → running → succeeded | failed | cancelled`. Luồng xử lý: (1) API ghi bản ghi job vào CSDL, đẩy vào hàng đợi và trả `202 Accepted` kèm `job_id`; (2) frontend mở kết nối SSE `GET /api/v1/jobs/{job_id}/events`; (3) worker phát sự kiện tiến trình lên kênh Redis `job:{id}`, API chuyển tiếp thành sự kiện SSE; (4) khi job kết thúc, frontend làm mới dữ liệu liên quan bằng TanStack Query. Job có thể hủy (`POST /jobs/{id}/cancel`): worker kiểm tra cờ hủy giữa các bước. Các bước ghi CSDL được thiết kế lũy đẳng (idempotent) để chạy lại an toàn khi worker khởi động lại.

```
event: progress
data: {"job_id":"8f1c…","stage":"testing","operation":"GET /books","done":37,"total":120,
       "outcomes":{"ACCEPT":22,"REJECT":13,"SERVER_ERR":0,"OTHER":2}}

event: finished
data: {"job_id":"8f1c…","status":"succeeded","result_ref":"/api/v1/test-runs/41"}
```

# 5. THIẾT KẾ CHI TIẾT CÁC MÔ-ĐUN

## 5.1. M1 – Nạp và tiền xử lý tài liệu

**Đầu vào được hỗ trợ:** URL một trang (tải bằng httpx; trang render bằng JavaScript có thể dùng Playwright – mở rộng), tệp HTML, Markdown, PDF, TXT, hoặc văn bản dán trực tiếp. Mọi đầu vào được chuẩn hóa về **Markdown** vì định dạng này giữ được tiêu đề, bảng và khối mã – ba cấu trúc mang nhiều thông tin API nhất.

**Các bước xử lý:**

1. Trích nội dung chính (trafilatura; dự phòng BeautifulSoup loại bỏ nav/footer/script), chuyển sang Markdown (markdownify), giữ nguyên khối mã và bảng.
1. Chuẩn hóa: gộp khoảng trắng, chuẩn hóa Unicode NFC, đánh số offset ký tự để mọi trích dẫn về sau ánh xạ được về vị trí gốc.
1. Phát hiện chữ ký operation bằng biểu thức chính quy `\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[\w\-./{}:]*)` và lệnh mẫu dạng `curl -X <METHOD> <URL>`.
1. Phân đoạn: mỗi chữ ký mở một phân đoạn, kéo dài đến chữ ký kế tiếp hoặc tiêu đề cùng cấp; nếu tài liệu không có chữ ký tường minh, dùng cây tiêu đề và – cuối cùng – nhờ LLM đề xuất ranh giới.
1. Đánh dấu **ngữ cảnh chung**: các mục xác thực, phân trang, mã lỗi chung, tham số dùng chung được gắn cờ `global=true` và được chèn (có giới hạn token) vào prompt của mọi phân đoạn.
1. Kiểm soát độ dài: phân đoạn vượt ngưỡng (mặc định ~3.000 token) được tách tiếp theo tiêu đề con để tránh output bị cắt cụt.

```
Chunk {
  id: uuid, document_id: uuid, order: int,
  title: "List books", operation_hint: {method: "GET", path: "/v1/books"},
  text: "...markdown...", token_count: 412,
  source_span: {start: 10234, end: 11980},   // offset trong văn bản chuẩn hóa
  is_global: false
}
```

## 5.2. M2 – Sinh OAS bằng LLM

### 5.2.1. Chiến lược hai pha: trích xuất rồi lắp ráp

Thay vì yêu cầu LLM viết thẳng toàn bộ YAML, hệ thống tách thành hai pha. **Pha trích xuất:** với mỗi phân đoạn, LLM trả về một **IR** dạng JSON theo schema cố định (Phụ lục B), mỗi phần tử kèm trích dẫn nguyên văn. **Pha lắp ráp:** mã Python xác định (deterministic) chuyển các IR thành OAS 3.0.3. Cách làm này giúp: output nhỏ và có cấu trúc nên ít lỗi cú pháp; kiểm tra được bằng Pydantic; lưu được bằng chứng cho từng phần tử; và tách bạch phần “hiểu tài liệu” (LLM) với phần “tuân thủ chuẩn” (mã).

### 5.2.2. Gọi LLM

- Prompt hệ thống quy định: chỉ trích thông tin có trong văn bản, không suy đoán; mỗi phần tử phải có `evidence` trích nguyên văn; thiếu thông tin thì bỏ trống (Phụ lục A).
- Dùng **structured output** theo JSON Schema khi nhà cung cấp hỗ trợ; nếu không, dùng chế độ JSON và kiểm tra bằng Pydantic. Lỗi parse/validate → gửi lại kèm thông báo lỗi, tối đa 2 lần.
- Nhiệt độ 0 (hoặc thấp nhất cho phép), giới hạn token đầu ra theo kích thước phân đoạn; ghi lại mô hình, phiên bản, seed (nếu hỗ trợ), số token, độ trễ vào bảng `llm_call`.
- Các phân đoạn độc lập được gọi song song có giới hạn (semaphore) để tôn trọng hạn mức của nhà cung cấp; kết quả được cache theo (mô hình, hash prompt).

### 5.2.3. Lắp ráp IR → OAS 3.0.3

- **Đường dẫn:** tách base URL vào `servers`; chuẩn hóa biến đường dẫn về dạng `{name}`; mọi tham số path tự động `required: true` (bắt buộc theo chuẩn).
- **Gộp trùng:** các IR cùng (method, path) được hợp nhất; xung đột thuộc tính giữ giá trị có trích dẫn cụ thể hơn và ghi cảnh báo.
- **Schema dùng chung:** schema request/response được chuẩn hóa (sắp xếp khóa) rồi băm; schema trùng băm đưa vào `components/schemas` và thay bằng `$ref`.
- **Ràng buộc:** ánh xạ theo Bảng 6; phụ thuộc giữa tham số lưu ở phần mở rộng `x-dependencies` theo cú pháp kiểu IDL [Martin-Lopez et al.] vì OAS 3.0 không biểu diễn trực tiếp.
- **Bằng chứng:** không nhúng vào đặc tả để giữ đặc tả sạch; lưu ở bảng `evidence` với khóa là JSON Pointer của phần tử (ví dụ `/paths/~1books/get/parameters/0/schema/maximum`). Khi xuất có thể bật tùy chọn kèm `x-evidence`.

**Bảng 6. Ánh xạ ràng buộc từ IR sang OAS 3.0.3**

| IR (kind) | Từ khóa OAS 3.0.3 | Ghi chú |
|---|---|---|
| required | `parameters[].required`, `schema.required[]` | Tham số path luôn `true`. |
| type / format | `type`, `format` | format: date, date-time, email, uuid, uri, int32, int64… |
| minimum / maximum | `minimum`, `maximum` |  |
| exclusiveMin/Max | `exclusiveMinimum: true` + `minimum` | OAS 3.0 dùng boolean (khác 3.1 dùng số). |
| minLength / maxLength | `minLength`, `maxLength` |  |
| pattern | `pattern` | Biểu thức chính quy ECMA-262. |
| enum | `enum` | So khớp như tập hợp khi chấm điểm. |
| minItems / maxItems / unique | `minItems`, `maxItems`, `uniqueItems` |  |
| default | `default` | Phải thỏa các ràng buộc khác (luật lint). |
| nullable | `nullable: true` | OAS 3.1 thay bằng `type: [x, "null"]`. |
| dependency | `x-dependencies: ["IF order THEN sort;"]` | Requires, Or, OnlyOne, AllOrNone, ZeroOrOne, quan hệ số học. |

### 5.2.4. Vòng tự sửa lỗi

Sau lắp ráp, đặc tả được kiểm tra bằng openapi-spec-validator. Lỗi được xử lý theo thứ tự: (1) **sửa xác định** bằng luật – thêm tham số path còn thiếu, thêm response mặc định khi operation không có response, đổi tên `operationId` trùng; (2) lỗi còn lại được gửi cho LLM kèm đoạn đặc tả liên quan để sửa cục bộ, tối đa 2 vòng. Đặc tả sau vòng sửa được lưu thành phiên bản có nhãn `repaired` để thực nghiệm so sánh cấu hình C0 và C1.

## 5.3. M3 – Đánh giá OAS

**Bảng 7. Năm mức đánh giá đặc tả**

| Mức | Nội dung | Công cụ / cách làm |
|---|---|---|
| L1 – Parse | Output là YAML/JSON đọc được. | ruamel.yaml |
| L2 – Hợp lệ | Tuân thủ OAS 3.0.3 (cấu trúc, kiểu, `$ref` phân giải được). | openapi-spec-validator |
| L3 – Lint | Mỗi operation có ≥ 1 response 2xx; tham số path khai báo đủ; `operationId` duy nhất; enum không rỗng; min ≤ max; default thỏa ràng buộc; ví dụ (example) thỏa schema. | Bộ luật Python (có thể dùng thêm Spectral) |
| L4 – Grounding | Mỗi phần tử có trích dẫn tìm thấy trong tài liệu (so khớp mờ, ngưỡng ≥ 90/100); phần tử không có căn cứ bị gắn cờ “nghi hallucination”. | rapidfuzz.partial_ratio |
| L5 – So với GT | Phân rã thành atomic facts và so khớp với đặc tả chuẩn. | fact_matcher + metrics |

**Atomic facts và chuẩn hóa.** Mỗi đặc tả được phân rã thành năm nhóm fact: *endpoint* (METHOD, path chuẩn hóa); *parameter* (operation, in, name, required, type); *request body* (operation, media type, đường dẫn thuộc tính, type, required); *response* (operation, status, đường dẫn thuộc tính, type); *constraint* (operation, vị trí, tên, từ khóa, giá trị). Khi so khớp: tên biến đường dẫn được bỏ qua (`{id}` ≡ `{bookId}`), tên header không phân biệt hoa thường, enum so như tập hợp, số so theo giá trị, `$ref` được phân giải trước.

**Chỉ số.** Với F_sinh là tập fact của đặc tả sinh ra và F_GT là tập fact chuẩn:

- Precision = |F_sinh ∩ F_GT| / |F_sinh|;  Recall = |F_sinh ∩ F_GT| / |F_GT|;  F1 = 2·P·R / (P + R).
- Hallucination rate = số fact không có căn cứ trong tài liệu và không có trong GT / |F_sinh|;  Omission rate = 1 − Recall.
- Tổng hợp **macro** (trung bình theo API) và **micro** (gộp toàn bộ fact); báo cáo riêng từng nhóm fact, đặc biệt nhóm constraint.

## 5.4. M4 – Kiểm thử API và thu thập phản hồi

### 5.4.1. Request cơ sở và nguyên tắc một-biến

Để quy được kết quả về một tham số cụ thể, mỗi operation cần một **request cơ sở** đã biết được chấp nhận (2xx). Request cơ sở lấy theo thứ tự ưu tiên: ví dụ trong tài liệu/IR → giá trị `default` → các ca Schemathesis hợp lệ đã trả 2xx. Mọi probe chỉ **thay đổi một yếu tố** so với request cơ sở (one-factor-at-a-time); probe phụ thuộc giữa tham số là ngoại lệ có chủ đích và thay đổi theo cặp.

### 5.4.2. Các chiến lược kiểm thử

**Bảng 8. Chiến lược sinh ca kiểm thử**

| Mã | Chiến lược | Cách làm | Phát hiện chính |
|---|---|---|---|
| S1 | Schemathesis – dữ liệu hợp lệ | Sinh dữ liệu thỏa đặc tả; checks: `positive_data_acceptance`, `response_schema_conformance`, `status_code_conformance`, `content_type_conformance`, `not_a_server_error`. | D1, D7, D8, D0 |
| S2 | Schemathesis – dữ liệu vi phạm | Sinh dữ liệu vi phạm đặc tả; check `negative_data_rejection`. | D2, D3 |
| S3 | Probe bắt buộc | Bỏ từng tham số `required`; thêm/bỏ tham số tùy chọn. | D4 |
| S4 | Probe kiểu | Giá trị sai kiểu (chuỗi cho integer, số thực cho integer, mảng cho chuỗi…). | D6 |
| S5 | Probe enum | Giá trị ngoài enum; thu thập giá trị xuất hiện trong phản hồi. | D5 |
| S6 | Probe biên | min−1, min, max, max+1; khi chưa biết biên: tìm kiếm mũ + nhị phân (mục 5.5.2). Áp dụng cho số, độ dài chuỗi, số phần tử mảng. | D1, D3 |
| S7 | Probe định dạng/pattern | Email, ngày, uuid sai định dạng; chuỗi vi phạm pattern. | D1, D6 |
| S8 | Probe phụ thuộc | Tổ hợp cặp (pairwise) có/không của các tham số tùy chọn, trong ngân sách. | D9 |
| S9 | Lấy mẫu phản hồi | Gọi lặp với đầu vào đa dạng để thu nhiều body phản hồi. | D8 |

### 5.4.3. Phân loại kết quả một observation

Mỗi phản hồi được gán một nhãn: **ACCEPT** (2xx), **REJECT** (400, 422 – lỗi kiểm tra dữ liệu), **AUTH** (401, 403), **NOT_FOUND** (404), **RATE** (429), **SERVER_ERR** (5xx), **OTHER**. Chỉ ACCEPT/REJECT được dùng làm bằng chứng ràng buộc. 404 với tham số path chỉ được dùng khi request cơ sở cùng tài nguyên đã trả 2xx. SERVER_ERR được ghi nhận là **lỗi tiềm ẩn** (D0) – thường do API thiếu kiểm tra đầu vào – và không tự động sửa đặc tả. Probe cho kết quả không nhất quán giữa các lần lặp được chạy lại (mặc định 2 lần) và đánh dấu “không ổn định” nếu vẫn lệch.

### 5.4.4. An toàn và vết kiểm thử

- Danh sách host được phép theo dự án; chặn địa chỉ loopback, link-local và dải IP riêng (chống SSRF), trừ mạng Docker sandbox được cấu hình.
- Chế độ **safe** (mặc định với API công khai): chỉ GET/HEAD/OPTIONS; chế độ **full** (sandbox): cho phép POST/PUT/PATCH/DELETE, khôi phục dữ liệu sandbox giữa các lượt chạy.
- Giới hạn tốc độ (mặc định ≤ 5 request/giây với sandbox, ≤ 1 request/giây với API công khai), ngân sách request theo operation (mặc định 150 với sandbox, 30 với API công khai), timeout 10 giây; dừng khi gặp 429 liên tiếp.
- Header xác thực và trường nhạy cảm được che trước khi lưu vết và trước khi gửi nội dung cho LLM.

```
Observation {
  id, test_run_id, operation_id: "GET /books", strategy: "S6.boundary",
  probe: {param: "limit", in: "query", value: 101, baseline_id: "b-17"},
  request:  {method: "GET", url: "/v1/books?limit=101&sort=title", headers: {...redacted}},
  status_code: 400, latency_ms: 38.2,
  response: {headers: {"content-type": "application/json"},
             body: {"error": "limit must be between 1 and 100"}},
  outcome: "REJECT", repeat_index: 0, created_at
}
```

## 5.5. M5 – Phát hiện sai lệch và tinh chỉnh ràng buộc

### 5.5.1. Phân loại sai lệch

**Bảng 9. Danh mục sai lệch D0–D9**

| Mã | Loại sai lệch | Dấu hiệu từ phản hồi | Hành động đề xuất |
|---|---|---|---|
| D1 | Thiếu ràng buộc | Giá trị hợp lệ theo đặc tả bị REJECT nhất quán (`positive_data_acceptance` thất bại). | `add` minimum/maximum/enum/pattern/length… |
| D2 | Ràng buộc quá chặt | Giá trị vi phạm đặc tả lại được ACCEPT (`negative_data_rejection` thất bại). | `remove`/nới ràng buộc hoặc báo mâu thuẫn |
| D3 | Sai giá trị biên | Biên quan sát khác biên khai báo. | `replace` giá trị biên |
| D4 | Sai tính bắt buộc | Bỏ tham số `required` vẫn ACCEPT; hoặc thiếu tham số thì REJECT với thông báo nêu tên. | `replace` required |
| D5 | Sai/thiếu enum | Giá trị ngoài enum được ACCEPT; thông báo lỗi liệt kê tập giá trị khác. | `replace` enum |
| D6 | Sai kiểu/định dạng | Kiểu/định dạng khai báo không khớp hành vi. | `replace` type/format |
| D7 | Mã trạng thái chưa khai báo | `status_code_conformance` thất bại. | `add` response |
| D8 | Lệch schema phản hồi | `response_schema_conformance` thất bại: thiếu/thừa thuộc tính, sai kiểu, gặp null. | `add`/`replace` trong schema phản hồi |
| D9 | Phụ thuộc giữa tham số | Tổ hợp bị REJECT dù từng tham số hợp lệ riêng lẻ. | `add` x-dependencies |
| D0 | Lỗi máy chủ | 5xx với đầu vào bất kỳ. | Báo cáo lỗi; không sửa đặc tả tự động |

*Hình 3. Cây quyết định phân loại sai lệch từ observation (xem sơ đồ trong bản .docx)*

### 5.5.2. Thuật toán dò biên

Khi tham số số học chưa có biên trong đặc tả (hoặc cần kiểm chứng biên đã khai báo), hệ thống dò biên trên bằng **tìm kiếm mũ** để tìm giá trị đầu tiên bị từ chối, rồi **tìm kiếm nhị phân** trong khoảng (giá trị được chấp nhận lớn nhất, giá trị bị từ chối nhỏ nhất). Số probe là O(log U) với U là độ lớn của biên. Biên dưới làm đối xứng (kể cả số âm); số thực dừng khi khoảng nhỏ hơn ε; độ dài chuỗi và số phần tử mảng dùng cùng thuật toán trên độ dài.

```
def find_upper_bound(op, param, baseline, ok, budget, cap=10**9):
    """ok: một giá trị đã biết được ACCEPT (example/default). Trả về maximum (bao gồm) hoặc None."""
    hi = max(1, 2 * ok)
    while budget > 0:                        # 1) tìm kiếm mũ
        out = probe(op, baseline, param, hi); budget -= 1
        if out == ACCEPT:
            ok, hi = hi, hi * 2
            if hi > cap: return None         # không có biên trên trong phạm vi hợp lý
        elif out == REJECT: break
        else: return UNKNOWN                 # 5xx/401/429...: không đủ bằng chứng
    while hi - ok > 1 and budget > 0:        # 2) tìm kiếm nhị phân trong (ok, hi)
        mid = (ok + hi) // 2
        out = probe(op, baseline, param, mid); budget -= 1
        if out == ACCEPT: ok = mid
        elif out == REJECT: hi = mid
        else: return UNKNOWN
    # 3) xác nhận: ok phải ACCEPT, ok+1 phải REJECT (giả định miền chấp nhận là một khoảng)
    return ok if confirm(op, baseline, param, ok, ok + 1) else UNKNOWN
```

Với ví dụ Bookstore-Lab (default = 20): 40 → ACCEPT, 80 → ACCEPT, 160 → REJECT; nhị phân 120 → R, 100 → A, 110 → R, 105 → R, 102 → R, 101 → R; xác nhận 100/101. Tổng cộng 11 request để xác định `maximum = 100`.

### 5.5.3. Khai thác thông báo lỗi

Thông báo lỗi thường chứa chính ràng buộc. Hệ thống áp dụng hai tầng: (1) **thư viện mẫu regex** cho các dạng phổ biến (“must be between X and Y”, “must be (less|greater) than (or equal to) X”, “is required”, “must be one of […]”, “invalid format for X”, “length must be at most N”…); (2) nếu không khớp mẫu, gửi thông báo lỗi (đã che dữ liệu nhạy cảm) cho LLM với JSON Schema đầu ra `{param, kind, value, confidence}`. Kết quả của tầng (2) chỉ là **giả thuyết** và luôn được kiểm chứng bằng probe trước khi tạo đề xuất.

### 5.5.4. Suy diễn schema phản hồi

Với mỗi cặp (operation, status), hệ thống gom N mẫu body (mặc định tối thiểu 20 khi có thể) và dùng genson để suy diễn JSON Schema, sau đó so với schema khai báo: thuộc tính xuất hiện nhưng chưa khai báo; thuộc tính khai báo nhưng không bao giờ xuất hiện; tập kiểu quan sát được; có giá trị null hay không. Đề xuất `required` cho thuộc tính phản hồi chỉ khi thuộc tính có mặt ở 100% của ≥ 20 mẫu và tài liệu không nói là tùy chọn; đề xuất `enum` cho phản hồi chỉ ở mức gợi ý (độ tin cậy thấp) vì tập giá trị quan sát được có thể chưa đầy đủ.

### 5.5.5. Kết hợp bằng chứng tài liệu và runtime

**Bảng 10. Chính sách kết hợp bằng chứng**

| Tài liệu | Runtime | Kết luận | Hành động |
|---|---|---|---|
| Có nêu X | Khớp X | Xác nhận | Gắn nhãn `verified`, tăng độ tin cậy |
| Không nêu | Quan sát được X | Bổ sung | Đề xuất thêm X (nguồn: runtime) |
| Có nêu X | Mâu thuẫn (quan sát Y) | Mâu thuẫn tài liệu – cài đặt | Chế độ **descriptive**: đề xuất theo runtime. Chế độ **prescriptive**: giữ X, tạo báo cáo lỗi cài đặt. Không bao giờ tự động chấp nhận. |
| Có nêu X | Không kiểm chứng được | Chưa xác minh | Giữ X, gắn nhãn `unverified` (thiếu quyền, hết ngân sách, phương thức bị chặn) |

Chế độ **descriptive** (đặc tả mô tả đúng cái API đang làm) phù hợp khi mục tiêu là sinh test/mock chính xác; chế độ **prescriptive** (đặc tả là hợp đồng mong muốn) phù hợp khi mục tiêu là phát hiện lỗi cài đặt. Người dùng chọn chế độ theo dự án; thực nghiệm của đề tài dùng chế độ descriptive và báo cáo riêng số mâu thuẫn tài liệu – cài đặt.

### 5.5.6. Độ tin cậy của đề xuất

Mỗi đề xuất tổng hợp nhiều **kênh bằng chứng** độc lập; độ tin cậy được tính theo mô hình noisy-OR:

**conf = 1 − ∏ₖ (1 − rₖ)**

- **Kênh probe:** r = cận dưới Wilson của tỷ lệ quan sát ủng hộ s/n (n gồm cả quan sát mâu thuẫn), z = 1,96: r = [p̂ + z²/2n − z·√(p̂(1−p̂)/n + z²/4n²)] / (1 + z²/n). Ví dụ 6/6 quan sát nhất quán → r ≈ 0,61.
- **Kênh thông báo lỗi:** r = 0,8 nếu khớp mẫu regex và giá trị trùng biên dò được; r = 0,6 nếu do LLM trích và đã được probe xác nhận.
- **Kênh tài liệu:** r = 0,7 khi tài liệu nêu cùng ràng buộc (trường hợp “xác nhận”).
- **Kênh lấy mẫu phản hồi:** r = cận dưới Wilson của tần suất quan sát trên số mẫu.

Ví dụ D1 của `limit`: kênh probe 0,61 và kênh thông báo lỗi 0,8 → conf = 1 − 0,39 × 0,2 ≈ 0,92. Ngưỡng mặc định: **≥ 0,8** tin cậy cao (được phép tự động chấp nhận ở chế độ vòng lặp tự động, trừ trường hợp mâu thuẫn tài liệu); **0,5–0,8** cần duyệt; **< 0,5** chỉ hiển thị như gợi ý. Các hệ số là tham số cấu hình, được hiệu chỉnh trên tập phát triển và cố định trước khi chạy tập đánh giá.

### 5.5.7. Định dạng đề xuất

```
{
  "id": "p-0193", "finding_id": "f-0071", "code": "D1",
  "target": "/paths/~1books/get/parameters/0/schema",
  "json_patch": [
    {"op": "add", "path": "/paths/~1books/get/parameters/0/schema/minimum", "value": 1},
    {"op": "add", "path": "/paths/~1books/get/parameters/0/schema/maximum", "value": 100}
  ],
  "evidence": {
    "doc":     [{"chunk_id": "c-12", "quote": "limit — Number of books per page. Defaults to 20."}],
    "runtime": ["obs-5512", "obs-5513", "obs-5518", "obs-5519", "obs-5520", "obs-5521"],
    "message": "limit must be between 1 and 100"
  },
  "channels": {"probe": 0.61, "error_message": 0.80},
  "confidence": 0.92, "doc_conflict": false,
  "status": "pending"            // pending | accepted | rejected | edited | applied | verified
}
```

### 5.5.8. Vòng lặp tinh chỉnh

*Hình 4. Trình tự một vòng kiểm thử – phát hiện – duyệt – tạo phiên bản (xem sơ đồ trong bản .docx)*

**Điều kiện dừng:** không còn finding mới có độ tin cậy ≥ τ (mặc định 0,5), hoặc đạt số vòng tối đa K (mặc định 3), hoặc hết ngân sách request của dự án. **Kiểm thử hồi quy:** sau khi áp dụng đề xuất, các probe liên quan được chạy lại; finding được chuyển `verified` nếu hết sai lệch, mở lại nếu chưa. **Xung đột:** hai đề xuất tác động cùng JSON Pointer được gộp nếu tương thích, ngược lại giữ đề xuất có độ tin cậy cao hơn và gắn cờ xung đột để người dùng quyết định.

## 5.6. M6 – Quản lý phiên bản và xuất bản

- Phiên bản đặc tả **bất biến**; mỗi phiên bản lưu `parent_id`, nội dung đầy đủ (JSONB) và JSON Patch so với phiên bản cha; nhãn gợi ý: `generated`, `repaired`, `refined-k`, `manual`.
- Sửa tay trên trình soạn YAML cũng tạo phiên bản mới (nhãn `manual`) sau khi qua kiểm tra hợp lệ.
- So sánh: diff văn bản YAML (Monaco DiffEditor) và diff ngữ nghĩa trên JSON (deepdiff) hiển thị theo operation.
- Xuất: YAML hoặc JSON, tùy chọn loại bỏ phần mở rộng `x-*`, kèm báo cáo thay đổi (danh sách đề xuất đã áp dụng và bằng chứng).

# 6. THIẾT KẾ CƠ SỞ DỮ LIỆU

*Hình 5. Sơ đồ thực thể – liên kết (rút gọn, không hiển thị thuộc tính) (xem sơ đồ trong bản .docx)*

**Bảng 11. Các bảng chính**

| Bảng | Cột chính | Mô tả |
|---|---|---|
| project | id, name, base_url, auth_config (mã hóa), allowed_hosts[], mode (safe/full), policy (descriptive/prescriptive) | Dự án và cấu hình kiểm thử mặc định. |
| document | id, project_id, source_type, source_uri, raw_path, markdown, sha256 | Tài liệu gốc và bản Markdown chuẩn hóa. |
| chunk | id, document_id, order, title, operation_hint, text, token_count, span_start, span_end, is_global | Phân đoạn tài liệu. |
| spec_version | id, project_id, parent_id, version_no, label, content (JSONB), patch_from_parent (JSONB), model, created_by, created_at | Phiên bản đặc tả bất biến; quan hệ cha – con. |
| evidence | id, spec_version_id, json_pointer, chunk_id, quote, match_score | Trích dẫn tài liệu cho từng phần tử đặc tả. |
| ground_truth | id, project_id, kind (doc/behavior), content (JSONB), note | Đặc tả chuẩn dùng để chấm điểm. |
| evaluation | id, spec_version_id, ground_truth_id, metrics (JSONB), facts (JSONB), lint_issues (JSONB) | Kết quả đánh giá L1–L5. |
| test_run | id, spec_version_id, config (JSONB), status, started_at, finished_at, stats (JSONB) | Một lượt kiểm thử. |
| observation | id, test_run_id, operation_id, strategy, probe (JSONB), request (JSONB), status_code, response (JSONB), outcome, latency_ms, repeat_index | Vết request/response (bảng lớn nhất; đánh chỉ mục theo test_run_id, operation_id). |
| finding | id, test_run_id, code (D0–D9), operation_id, json_pointer, summary, confidence, doc_conflict, status | Sai lệch phát hiện được. |
| finding_observation | finding_id, observation_id, role (support/contradict) | Liên kết nhiều – nhiều finding ↔ observation. |
| proposal | id, finding_id, json_patch (JSONB), channels (JSONB), confidence, status, applied_version_id, reviewed_by, reviewed_at | Đề xuất chỉnh sửa và trạng thái duyệt. |
| job | id, project_id, type, status, progress (JSONB), error, created_at | Tác vụ nền. |
| llm_call | id, job_id, provider, model, prompt_hash, input_tokens, output_tokens, latency_ms, cost_usd, cached | Nhật ký gọi LLM phục vụ đo chi phí thực nghiệm. |

# 7. THIẾT KẾ API BACKEND (FASTAPI)

## 7.1. Quy ước

- Tiền tố `/api/v1`; dữ liệu JSON; phân trang `?page=&size=`; thời gian ISO 8601 (UTC).
- Tác vụ dài trả `202 Accepted` + `{job_id}`; theo dõi qua `GET /jobs/{id}` hoặc SSE `GET /jobs/{id}/events`.
- Lỗi theo RFC 7807 (`application/problem+json`): `{type, title, status, detail, instance, errors[]}`.
- FastAPI tự sinh `/openapi.json` cho chính backend; frontend sinh client TypeScript từ tệp này. Bản thân backend cũng có thể được nạp làm một dự án để hệ thống tự kiểm thử (dogfooding).

## 7.2. Danh sách endpoint

**Bảng 12. Endpoint của backend**

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| POST / GET | /projects | Tạo / liệt kê dự án |
| GET / PATCH / DELETE | /projects/{id} | Xem / sửa / xóa dự án |
| POST | /projects/{id}/documents | Nạp tài liệu (multipart tệp, hoặc JSON {url} / {text}) |
| GET | /documents/{id}/chunks | Danh sách phân đoạn |
| PATCH / POST | /chunks/{id}  ·  /documents/{id}/resegment | Sửa phân đoạn  ·  phân đoạn lại |
| POST | /projects/{id}/generate | Sinh OAS (body: model, options) → 202 |
| GET | /projects/{id}/specs | Danh sách phiên bản đặc tả |
| GET | /specs/{id}?format=yaml\|json | Nội dung một phiên bản |
| POST | /specs/{id}/versions | Tạo phiên bản từ chỉnh sửa tay |
| GET | /specs/{id}/evidence?pointer= | Bằng chứng của một phần tử |
| POST | /specs/{id}/validate | Kiểm tra L1–L4 (đồng bộ) |
| POST | /projects/{id}/ground-truths | Upload đặc tả chuẩn |
| POST / GET | /specs/{id}/evaluations  ·  /evaluations/{id} | Đánh giá với GT → 202  ·  xem kết quả |
| POST | /specs/{id}/test-runs | Chạy kiểm thử (body: cấu hình) → 202 |
| GET | /test-runs/{id}  ·  /test-runs/{id}/observations | Trạng thái, thống kê  ·  vết (lọc, phân trang) |
| POST | /test-runs/{id}/cancel | Hủy lượt kiểm thử |
| GET | /test-runs/{id}/findings  ·  /findings/{id} | Danh sách / chi tiết sai lệch |
| GET | /specs/{id}/proposals?status= | Danh sách đề xuất |
| POST | /proposals/{id}/accept  ·  /reject | Chấp nhận / từ chối |
| PATCH | /proposals/{id} | Sửa JSON Patch của đề xuất |
| POST | /specs/{id}/apply | Áp dụng {proposal_ids} → phiên bản mới (201) |
| POST | /specs/{id}/refine-loop | Vòng lặp tự động (max_iter, auto_accept_threshold) → 202 |
| GET | /specs/{id}/diff?against= | So sánh hai phiên bản |
| GET | /specs/{id}/export?format=&strip_extensions= | Xuất đặc tả |
| GET | /jobs/{id}  ·  /jobs/{id}/events | Trạng thái job  ·  luồng SSE |
| POST / GET | /experiments  ·  /experiments/{id}/results | Chạy ma trận thực nghiệm  ·  kết quả tổng hợp |
| GET | /llm/providers  ·  /health | Nhà cung cấp LLM khả dụng  ·  kiểm tra sức khỏe |

## 7.3. Ví dụ: tạo lượt kiểm thử

```
POST /api/v1/specs/9b2e…/test-runs
{
  "base_url": "http://bookstore-lab:8000/v1",
  "auth": {"type": "bearer", "secret_ref": "sec_01"},
  "mode": "full",
  "strategies": ["S1","S2","S3","S4","S5","S6","S7","S9"],
  "budget_per_operation": 150, "max_rps": 5, "timeout_s": 10,
  "seed": 42, "operations": ["GET /books", "GET /books/{id}", "POST /orders"]
}

HTTP/1.1 202 Accepted
{"test_run_id": 41, "job_id": "8f1c…", "status": "queued"}
```

# 8. THIẾT KẾ GIAO DIỆN (REACTJS)

## 8.1. Danh sách màn hình

**Bảng 13. Màn hình chính**

| Mã | Màn hình | Thành phần chính |
|---|---|---|
| SC-01 | Tổng quan | Thẻ thống kê (dự án, phiên bản, finding mở, chi phí LLM); danh sách dự án gần đây. |
| SC-02 | Chi tiết dự án | Tabs: Tài liệu · Đặc tả · Đánh giá · Kiểm thử · Sai lệch & đề xuất · Phiên bản. |
| SC-03 | Nạp tài liệu & phân đoạn | Upload/URL/dán; danh sách phân đoạn có thể gộp/tách; xem trước Markdown. |
| SC-04 | Trình xem đặc tả | Ba khung: tài liệu (làm nổi bật trích dẫn) · YAML (Monaco) · Swagger UI; bấm một phần tử YAML → cuộn tới trích dẫn tương ứng; huy hiệu grounding. |
| SC-05 | Báo cáo đánh giá | Thẻ chỉ số; biểu đồ cột P/R/F1 theo nhóm fact; bảng fact TP/FP/FN; danh sách lỗi lint. |
| SC-06 | Cấu hình & chạy kiểm thử | Form cấu hình; thanh tiến trình theo operation (SSE); bộ đếm theo outcome; nút hủy. |
| SC-07 | Trình xem vết | Bảng observation có lọc; drawer chi tiết request/response; liên kết tới finding. |
| SC-08 | Sai lệch & đề xuất | Danh sách finding theo loại và độ tin cậy; chi tiết bằng chứng tài liệu + runtime; xem trước JSON Patch và YAML trước/sau; chấp nhận/từ chối/sửa; chấp nhận hàng loạt theo ngưỡng (Hình 6). |
| SC-09 | Phiên bản & diff | Dòng thời gian phiên bản; DiffEditor; danh sách đề xuất đã áp dụng ở mỗi phiên bản. |
| SC-10 | Thực nghiệm | Chọn API × mô hình × cấu hình × số lần lặp; theo dõi; biểu đồ F1 trước/sau, conformance; xuất CSV. |
| SC-11 | Cài đặt | Nhà cung cấp LLM, khóa API, mô hình mặc định, host được phép, hạn mức. |

*Hình 6. Bản mẫu màn hình SC-08 “Sai lệch & đề xuất” (số liệu minh họa) (xem sơ đồ trong bản .docx)*

## 8.2. Kiến trúc frontend

- **Dữ liệu server:** TanStack Query (cache theo khóa truy vấn, tự làm mới khi job hoàn tất); client API sinh tự động từ OpenAPI của backend (ví dụ openapi-typescript) để kiểu dữ liệu FE – BE luôn khớp.
- **Trạng thái giao diện:** Zustand (tab đang mở, bộ lọc, lựa chọn đề xuất).
- **Thời gian thực:** hook `useJobEvents(jobId)` bọc `EventSource`, tự kết nối lại và cập nhật cache khi nhận sự kiện `finished`.
- **Thành phần dùng lại:** `YamlEditor`, `DiffView`, `EvidencePanel`, `ConfidenceBar`, `PatchPreview`, `TraceTable`, `MetricCards`.
- **Chất lượng:** TypeScript strict, ESLint + Prettier, kiểm thử thành phần bằng Vitest, kiểm thử đầu-cuối luồng chính bằng Playwright.

# 9. THIẾT KẾ THỰC NGHIỆM VÀ ĐÁNH GIÁ

## 9.1. Câu hỏi nghiên cứu

- **RQ1:** OAS do LLM sinh từ tài liệu đạt chất lượng đến đâu theo từng nhóm thành phần, đặc biệt nhóm ràng buộc?
- **RQ2:** Phản hồi kiểm thử phát hiện sai lệch ràng buộc với độ chính xác (precision) và độ bao phủ (recall) bao nhiêu?
- **RQ3:** Tinh chỉnh dựa trên phản hồi cải thiện F1 ràng buộc và tỷ lệ phù hợp đặc tả – hành vi đến đâu, với chi phí (request, token, thời gian) như thế nào?

## 9.2. Bộ dữ liệu dự kiến

Tiêu chí chọn API: có tài liệu viết cho con người bằng tiếng Anh; có đặc tả chuẩn hoặc xây dựng được ground truth; có môi trường chạy được phép kiểm thử; đa dạng về số operation và loại ràng buộc. Danh sách cuối cùng chốt ở giai đoạn 2 sau khi kiểm tra khả năng truy cập, điều khoản sử dụng và giới hạn tốc độ.

**Bảng 14. Danh sách API ứng viên**

| Nhóm | API | Ground truth | Môi trường | Phạm vi kiểm thử |
|---|---|---|---|---|
| A – có kiểm soát | Bookstore-Lab (nhóm tự xây dựng bằng FastAPI, cài cắm sai lệch tài liệu – cài đặt có kiểm soát) | Hành vi biết trước chính xác | Docker cục bộ | Toàn bộ phương thức |
| A – tự triển khai | Swagger Petstore v3; RealWorld (Conduit) API | OAS chính thức, hiệu chỉnh theo hành vi | Docker cục bộ | Toàn bộ phương thức |
| B – công khai | LanguageTool, REST Countries, Genome Nexus, FDIC, OhSome, OMDb (các dịch vụ dùng trong NLP2REST/RESTGPT) | OAS công bố + luật ràng buộc đã gán nhãn của nghiên cứu trước (nếu có trong gói công bố) | API công khai hoặc tự triển khai (LanguageTool) | Chỉ phương thức đọc, giới hạn tốc độ |

**Ground truth hai lớp.** Với mỗi API, nhóm xây dựng (i) **GT tài liệu** – những gì tài liệu nêu – và (ii) **GT hành vi** – ràng buộc thực tế của cài đặt (biết trước với Bookstore-Lab; với API khác, GT tài liệu được hiệu chỉnh bằng kiểm chứng thủ công có ghi chép). RQ1 chấm theo GT tài liệu; RQ2–RQ3 chấm theo GT hành vi. Hai người gán nhãn độc lập, đo mức đồng thuận bằng Cohen’s kappa và thống nhất bất đồng trước khi chấm.

**Biến thể tài liệu lược ràng buộc.** Với nhóm A, tạo thêm bản tài liệu đã xóa có kiểm soát khoảng 30–50% câu mô tả ràng buộc để đo khả năng **phục hồi ràng buộc** chỉ nhờ phản hồi runtime.

## 9.3. Thiết lập thực nghiệm

- **Mô hình:** 2 LLM – một mô hình thương mại qua API và một mô hình trọng số mở chạy cục bộ (ví dụ Qwen2.5-7B-Instruct qua Ollama); phiên bản cụ thể được khóa tại thời điểm chạy.
- **Cấu hình:** C0 – chỉ LLM; C1 – LLM + vòng tự sửa lỗi theo validator; C2 – C1 + tinh chỉnh từ phản hồi kiểm thử (tối đa K = 3 vòng, chế độ descriptive, tự chấp nhận đề xuất ≥ 0,8 để loại bỏ ảnh hưởng chủ quan của người duyệt; các đề xuất 0,5–0,8 được ghi nhận và phân tích riêng).
- **Lặp lại:** 3 lần mỗi tổ hợp; ma trận chính 2 mô hình × 3 cấu hình × ~10 API × 3 lần ≈ 180 lượt; bổ sung biến thể lược ràng buộc trên nhóm A.
- **Ngân sách:** theo mục 5.4.4; ghi đủ số request, token, thời gian của mọi lượt.

## 9.4. Chỉ số đánh giá

**Bảng 15. Chỉ số theo câu hỏi nghiên cứu**

| RQ | Chỉ số | Định nghĩa |
|---|---|---|
| RQ1 | Parse / OAS validity | Tỷ lệ output parse được / hợp lệ OAS 3.0.3. |
| RQ1 | Lint density | Số lỗi lint trên mỗi operation. |
| RQ1 | P / R / F1 theo nhóm fact | Mục 5.3; macro theo API và micro toàn bộ. |
| RQ1 | Hallucination / Omission | Mục 5.3. |
| RQ2 | Finding precision | Số finding đúng (xác minh thủ công theo GT hành vi) / tổng finding báo cáo. |
| RQ2 | Discrepancy recall | Số sai lệch cài cắm (Bookstore-Lab) hoặc đã biết được phát hiện / tổng số sai lệch. |
| RQ2 | Constraint recovery | Số ràng buộc bị lược khỏi tài liệu được khôi phục đúng / số ràng buộc bị lược. |
| RQ3 | F1 ràng buộc & ΔF1 | F1 nhóm constraint theo GT hành vi ở phiên bản cuối so với C0/C1. |
| RQ3 | Conformance rate | Tỷ lệ check Schemathesis đạt trên một bộ test cố định, trước và sau tinh chỉnh. |
| RQ3 | Chi phí | Số request, token vào/ra, thời gian, chi phí API (USD) mỗi API; số vòng đến khi hội tụ. |

## 9.5. Phân tích thống kê

Đơn vị so sánh là **API** (ghép cặp giữa các cấu hình); ba lần lặp được tổng hợp bằng trung vị cho mỗi API và không coi là mẫu độc lập. So sánh C2 với C1 và C1 với C0 bằng **kiểm định Wilcoxon dấu-hạng** cho dữ liệu ghép cặp, hiệu chỉnh đa so sánh bằng **Holm**, báo cáo cỡ hiệu ứng r = Z/√N và **khoảng tin cậy bootstrap 95%** (10.000 lần lấy mẫu lại) cho trung bình ΔF1. Do số API nhỏ (~10), kết quả được diễn giải thận trọng, ưu tiên cỡ hiệu ứng và khoảng tin cậy hơn giá trị p.

## 9.6. Các mối đe dọa đến tính hợp lệ

- **Data contamination:** LLM có thể đã thấy OAS của API phổ biến → đưa vào Bookstore-Lab (chưa công bố) và so sánh kết quả giữa API phổ biến và ít phổ biến.
- **API công khai thay đổi theo thời gian:** lưu ảnh chụp (snapshot) vết và ngày chạy; chạy các cấu hình của cùng API trong cùng khoảng thời gian.
- **Tính chủ quan của GT:** hai người gán nhãn, đo Cohen’s kappa, công bố sổ tay gán nhãn.
- **Giả định miền chấp nhận là một khoảng:** có thể sai với ràng buộc phức tạp → bước xác nhận biên và nhãn UNKNOWN thay vì đề xuất sai.
- **Khái quát hóa:** số API hạn chế, chỉ tài liệu tiếng Anh và JSON → nêu rõ giới hạn trong báo cáo.

# 10. TRIỂN KHAI VÀ VẬN HÀNH

## 10.1. Docker Compose

**Bảng 16. Các dịch vụ triển khai**

| Dịch vụ | Ảnh / thành phần | Ghi chú |
|---|---|---|
| frontend | Nginx phục vụ bản build React | Cổng 80/443; reverse proxy `/api` → backend. |
| backend | Python + Uvicorn (FastAPI) | Chạy migration Alembic khi khởi động. |
| worker | Python + Arq | Có thể tăng số bản sao (scale) khi chạy thực nghiệm. |
| redis | Redis | Hàng đợi và pub/sub tiến trình. |
| postgres | PostgreSQL | Volume lưu dữ liệu bền vững. |
| ollama (tùy chọn) | Ollama + mô hình mở | Cần GPU hoặc chạy CPU với tốc độ thấp. |
| sut-* | bookstore-lab, petstore, conduit… | Nằm trong mạng riêng `sut-net`; có script khôi phục dữ liệu. |

**Bảng 17. Biến môi trường chính**

| Biến | Ý nghĩa |
|---|---|
| DATABASE_URL, REDIS_URL | Kết nối CSDL và Redis. |
| SECRET_KEY | Khóa mã hóa secret (Fernet) và ký phiên. |
| LLM_DEFAULT_PROVIDER, LLM_DEFAULT_MODEL | Nhà cung cấp và mô hình mặc định. |
| OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_BASE_URL | Thông tin truy cập LLM (chỉ khai báo cái dùng). |
| TEST_ALLOWED_NETWORKS | Dải mạng sandbox được phép (ví dụ mạng `sut-net`). |
| TEST_DEFAULT_RPS, TEST_DEFAULT_BUDGET, TEST_TIMEOUT_S | Hạn mức kiểm thử mặc định. |
| LLM_CACHE_ENABLED, LLM_MAX_CONCURRENCY | Bật cache và giới hạn số lời gọi đồng thời. |

## 10.2. Bảo mật

- Secret mã hóa khi lưu; chỉ giải mã trong worker lúc gửi request; không trả về qua API.
- Chống SSRF cho cả bộ tải tài liệu và bộ kiểm thử: phân giải DNS rồi kiểm tra IP trước khi kết nối; chặn chuyển hướng sang host không được phép.
- Giới hạn kích thước upload, làm sạch HTML trước khi hiển thị (tránh XSS), CORS chỉ cho phép origin của frontend.
- Che dữ liệu nhạy cảm (header xác thực, token, email) trong vết và trong nội dung gửi LLM.

## 10.3. Ghi log và giám sát

Log có cấu trúc (JSON) kèm `job_id`, `project_id`; bảng `llm_call` ghi token, độ trễ, chi phí; thống kê job (thời gian theo giai đoạn, số request, tỷ lệ lỗi) hiển thị ở trang Tổng quan.

## 10.4. Kiểm thử chính hệ thống

- **Đơn vị (pytest):** segmenter, assembler, ánh xạ ràng buộc, fact matcher, thuật toán dò biên (trên API giả lập), regex thông báo lỗi, tính độ tin cậy.
- **Tích hợp:** chạy toàn vòng lặp trên Bookstore-Lab với LLM giả lập (trả IR cố định) để kiểm tra phát hiện đủ các sai lệch cài cắm.
- **Frontend:** Vitest cho thành phần; Playwright cho luồng nạp tài liệu → sinh → kiểm thử → duyệt → xuất.

# 11. KẾ HOẠCH THỰC HIỆN VÀ RỦI RO

## 11.1. Mốc thực hiện

**Bảng 18. Mốc thực hiện (khớp tiến độ trong thuyết minh)**

| Mốc | Thời gian | Sản phẩm bàn giao | Tiêu chí hoàn thành |
|---|---|---|---|
| M1 | 10/2026 | Tổng quan, SRS, bộ dữ liệu sơ bộ | Chốt danh sách API, phạm vi MVP |
| M2 | 11/2026 | Tài liệu thiết kế (bản này), khung dự án FE/BE, Docker Compose | `docker compose up` chạy được khung; CI chạy test |
| M3 | 11–12/2026 | M1 + M2 + M3 (nạp, sinh, đánh giá) | Sinh OAS hợp lệ cho Bookstore-Lab và Petstore; báo cáo đánh giá có P/R/F1 |
| M4 | 12/2026–01/2027 | M4 (kiểm thử, vết) + màn hình SC-06, SC-07 | Chạy Schemathesis + probe; vết đầy đủ; an toàn kiểm thử hoạt động |
| M5 | 01–02/2027 | M5 + M6 + màn hình SC-08, SC-09 | Phát hiện đủ sai lệch cài cắm của Bookstore-Lab; áp dụng đề xuất, tạo phiên bản, kiểm thử hồi quy |
| M6 | 02–04/2027 | Thực nghiệm, phân tích, báo cáo, đóng gói | Bảng/biểu đồ RQ1–RQ3; mã nguồn và dữ liệu tái lập được |

**Ưu tiên khi thiếu thời gian:** giữ nguyên lõi nghiên cứu (M2, M4, M5 và FR-17 dạng script); cắt giảm theo thứ tự: tài khoản người dùng (FR-18) → vòng lặp tự động có giao diện (FR-14) → crawl nhiều trang → báo cáo HTML.

## 11.2. Rủi ro và giải pháp

**Bảng 19. Rủi ro chính**

| Rủi ro | Ảnh hưởng | Giải pháp |
|---|---|---|
| Output LLM sai định dạng hoặc bị cắt cụt | Không lắp ráp được đặc tả | Phân đoạn nhỏ, structured output, kiểm tra Pydantic, gửi lại kèm lỗi, vòng sửa lỗi |
| API công khai giới hạn tốc độ / chặn | Thiếu phản hồi cho RQ2–RQ3 | Ưu tiên nhóm A tự triển khai; ngân sách và tốc độ thấp; cache phản hồi; chạy ngoài giờ cao điểm |
| Ràng buộc không đơn điệu, phụ thuộc trạng thái | Dò biên sai | Bước xác nhận, nhãn UNKNOWN, khôi phục dữ liệu sandbox giữa các probe |
| Chi phí LLM vượt dự kiến | Không đủ lượt thực nghiệm | Cache theo hash prompt; dùng mô hình mở cục bộ; giới hạn token; ước lượng chi phí trước khi chạy |
| Trang tài liệu render bằng JavaScript | Không lấy được nội dung | Cho phép upload/dán; tùy chọn Playwright render |
| Thiếu thời gian hoàn thiện giao diện | Chậm tiến độ | Ưu tiên lõi + script thực nghiệm; giao diện theo thứ tự SC-04 → SC-08 → SC-06 |

# PHỤ LỤC A. PROMPT TRÍCH XUẤT IR (MẪU)

Prompt viết bằng tiếng Anh vì tài liệu đầu vào là tiếng Anh; nội dung trong `{…}` được hệ thống điền khi gọi.

```
[SYSTEM]
You are an API specification extractor. Read ONE documentation section and return ONLY a JSON
object that validates against the provided JSON Schema (OperationIR).
Rules:
1. Extract only facts explicitly stated in SECTION or GLOBAL CONTEXT. Never guess or use prior
   knowledge about this API.
2. For every parameter, body field, response and constraint, copy a verbatim quote (<= 200 chars)
   from the text into "evidence".
3. If a property is not stated (e.g. maximum, required), omit it. Do not invent defaults.
4. Normalize types to JSON Schema types: integer, number, string, boolean, array, object.
5. Write path variables as {name}; remove the server base URL from the path.
6. Express inter-parameter dependencies in IDL form, e.g. "IF order THEN sort;",
   "OnlyOne(isbn, title);", "AllOrNone(lat, lon);".
7. If SECTION does not describe an API operation, return {"operation": null}.

[USER]
GLOBAL CONTEXT (authentication, pagination, common errors):
{global_context}

SECTION:
{chunk_text}
```

# PHỤ LỤC B. MÔ HÌNH IR (PYDANTIC)

```
from typing import Any, Literal
from pydantic import BaseModel, Field

Kind = Literal["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength",
               "maxLength", "pattern", "enum", "format", "minItems", "maxItems",
               "uniqueItems", "default", "nullable"]

class ConstraintIR(BaseModel):
    kind: Kind
    value: Any
    evidence: str = Field(max_length=300)

class ParamIR(BaseModel):
    name: str
    location: Literal["query", "path", "header", "cookie"]
    type: Literal["integer", "number", "string", "boolean", "array", "object"] | None = None
    required: bool | None = None
    description: str | None = None
    constraints: list[ConstraintIR] = []
    evidence: str

class FieldIR(BaseModel):                 # thuộc tính trong body/response, ví dụ "items[].isbn"
    path: str
    type: str | None = None
    required: bool | None = None
    constraints: list[ConstraintIR] = []
    evidence: str | None = None

class BodyIR(BaseModel):
    media_type: str = "application/json"
    fields: list[FieldIR] = []
    example: Any | None = None
    evidence: str

class ResponseIR(BaseModel):
    status: str                           # "200", "4XX", "default"
    description: str | None = None
    fields: list[FieldIR] = []
    example: Any | None = None
    evidence: str

class DependencyIR(BaseModel):
    idl: str                              # "IF order THEN sort;"
    evidence: str

class OperationIR(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    path: str
    summary: str | None = None
    parameters: list[ParamIR] = []
    request_body: BodyIR | None = None
    responses: list[ResponseIR] = []
    dependencies: list[DependencyIR] = []
    security: list[str] = []
```

# PHỤ LỤC C. ĐẶC TẢ TRƯỚC VÀ SAU TINH CHỈNH (VÍ DỤ BOOKSTORE-LAB)

**Phiên bản v0** (nhãn `generated`) – sinh từ tài liệu:

```
paths:
  /books:
    get:
      parameters:
        - name: limit
          in: query
          schema: {type: integer, default: 20}
        - name: sort
          in: query
          required: true
          schema: {type: string, enum: [title, published_at]}
components:
  schemas:
    Book:
      properties:
        isbn: {type: string}
```

**Phiên bản v1** (nhãn `refined-1`) – sau khi chấp nhận các đề xuất D1, D4, D8:

```
paths:
  /books:
    get:
      parameters:
        - name: limit
          in: query
          schema: {type: integer, default: 20, minimum: 1, maximum: 100}   # D1, conf 0.92
        - name: sort
          in: query
          required: false                                                 # D4, descriptive
          schema: {type: string, enum: [title, published_at]}
components:
  schemas:
    Book:
      properties:
        isbn: {type: string, nullable: true}                              # D8
```
