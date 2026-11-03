# DECISIONS – các quyết định khi đặc tả chưa rõ

Nguyên tắc: chọn phương án đơn giản nhất chạy được, ghi lại ở đây. Các điểm “ghi đè TECH_SPEC” lấy từ PROMPT CHÍNH.

## 0. Dữ liệu đầu vào

| # | Vấn đề | Quyết định |
|---|---|---|
| 0.1 | Prompt yêu cầu `SpecLoop-Bench-v0.2.zip`, nhưng chỉ có **v0.1** (`Downloads/SpecLoop-Bench-v0.1.zip`). | Dùng v0.1. Bản này đủ `tools/`, `apis/bookstore-lab/` (SUT, GT tài liệu, GT hành vi, 13 sai lệch) nhưng **không có `examples/mini_loop/refine.py`**. |
| 0.2 | Không có prototype `refine.py` để port. | Cài đặt M4 + M5 trực tiếp theo TECH_SPEC 5.4–5.5 và giữ đúng thuật toán/ngưỡng ở đó: tìm kiếm mũ + nhị phân + bước xác nhận (5.5.2); cận dưới Wilson z = 1,96 và noisy-OR (5.5.6); r(regex) = 0,8, r(LLM) = 0,6, r(tài liệu) = 0,7; ngưỡng 0,8 (tự chấp nhận, trừ doc_conflict) / 0,5 (cần duyệt); ngân sách 150 (sandbox) / 30 (công khai); ≤ 5 / ≤ 1 req/s; timeout 10 s; K = 3, τ = 0,5. Khi có v0.2, nên chạy lại `tests/test_integration.py` và so sánh với `refine.py`. |

## 1. Kiến trúc (ghi đè TECH_SPEC theo PROMPT CHÍNH)

- SQLite + `Base.metadata.create_all` (không Alembic, không PostgreSQL). Cột JSON thay JSONB.
- Job nền: `ThreadJobRunner` (ThreadPoolExecutor) + bảng `job`; interface `JobRunner` tách riêng để thay bằng Redis/Arq sau.
- SSE `GET /jobs/{id}/events` đọc lại bảng `job` mỗi 0,5 s (đáp ứng NFR-01 ≤ 2 s), phát `progress` khi thay đổi và `finished` khi kết thúc.
- Khóa chính số nguyên cho mọi bảng, riêng `job.id` là chuỗi uuid hex.
- Để tránh khóa SQLite, mọi cập nhật tiến trình job được gọi sau khi transaction ghi khác đã commit.
- Thêm bảng phụ `llm_cache` (cache theo sha256(provider, model, prompt)) và `experiment` (lưu kết quả ma trận).
- Cổng: Bookstore-Lab 8000, backend 8001 (host; 8000 trong container), giao diện 3000 (docker) / 5173 (dev).

## 2. M1 – Nạp tài liệu

- Chuẩn hóa: NFC, CRLF→LF, bỏ khoảng trắng cuối dòng, gộp ≥ 3 dòng trống. Không gộp khoảng trắng trong dòng để giữ khối mã; mọi offset tính trên Markdown đã chuẩn hóa (lưu ở `document.markdown`).
- HTML: BeautifulSoup bỏ nav/footer/script… rồi markdownify (giữ code block, bảng); trafilatura chỉ là phương án dự phòng khi kết quả quá ngắn.
- Mục `global`: tiêu đề khớp auth/pagination/errors/conventions/rate limit/… và phần mở đầu tài liệu. Mục không chứa chữ ký operation nhưng là **tiêu đề tổ tiên** của operation (ví dụ “Books” chứa bảng thuộc tính Book) cũng được chèn vào ngữ cảnh của các operation con (không đánh dấu global).
- Chưa làm: crawl nhiều trang, nhờ LLM đề xuất ranh giới khi không có chữ ký/tiêu đề (cả tài liệu thành một phân đoạn rồi tách theo đoạn văn ≤ 3000 token).
- Đếm token xấp xỉ `len(text)/4` (không cài tiktoken).

## 3. M2 – Sinh OAS

- **FakeLLM** không trả IR cố định mà là một bộ trích xuất theo luật cho tài liệu Markdown dạng phổ biến (gạch đầu dòng `` `name` *(type, required)* – mô tả``, bảng thuộc tính, dòng `Response \`200 OK\``). Nó nhận đúng prompt của LLM thật và trả JSON → đi qua cùng đường parse/validate/retry. Dùng cho test và làm baseline offline (`model: "fake"`).
- Đầu ra LLM chấp nhận cả `{"operation": {...}}` lẫn đối tượng OperationIR trực tiếp. JSON mode (`response_format=json_object`); máy chủ không hỗ trợ thì tự gọi lại không có tham số này.
- Assembler: `requestBody.required = true` khi có ít nhất một thuộc tính bắt buộc (suy luận logic, không bịa giá trị). Response không liệt kê thuộc tính nhưng có ví dụ JSON → suy schema từ ví dụ (không suy `required`).
- Schema dùng chung: chỉ đưa vào `components/schemas` các object ≥ 2 thuộc tính xuất hiện ≥ 2 lần (băm JSON chuẩn hóa, bỏ description); tên lấy từ đoạn path số ít (`/books` → `Book`).
- Bằng chứng gắn tạm bằng khóa `x-ev`/`x-evk` trên nút, thu lại theo JSON Pointer sau khi bố trí xong rồi gỡ khỏi đặc tả. Xuất có thể kèm `x-evidence` (`include_evidence=true`).
- Vòng sửa lỗi: sửa xác định luôn chạy ở C1 (thêm tham số path thiếu, path param `required`, response mặc định, operationId trùng, mảng thiếu `items`, enum rỗng, exclusive* thiếu min/max). LLM sửa cục bộ ≤ 2 vòng chỉ khi còn lỗi validate và dùng LLM thật (FakeLLM bỏ qua). C0 = phiên bản `generated`; C1 = `repaired` (nếu sửa không thay đổi gì thì C1 = C0).
- Mô hình suy luận (qwen3…): `LLM_REASONING_EFFORT` gửi `reasoning_effort` qua endpoint OpenAI-compatible (Ollama hiểu
  `none` = tắt suy nghĩ). `LLM_STRUCTURED_OUTPUT` gửi `response_format=json_schema`: phân đoạn đã có chữ ký operation
  ép theo `OperationIR` (không cho trả null – mô hình nhỏ hay “lười” trả `{"operation": null}`), phân đoạn khác theo
  `ExtractionResult`. Cả hai tham số nằm trong khóa cache.
- Đọc JSON từ LLM: thử nguyên văn trước, chỉ bóc khối ```` ``` ```` khi toàn bộ đầu ra là một khối mã (trích dẫn hay chứa
  ```` ```json ```` chép từ tài liệu). Mã trạng thái kiểu `"200 OK"` được chuẩn hóa thành `"200"`.
- Ràng buộc LLM nêu nhưng không có giá trị (`minimum: null`, `enum: [null]`) bị bỏ; thuộc tính có tên không hợp lệ bị bỏ;
  vòng sửa lỗi xác định xóa tham số path không có trong đường dẫn.
- Không sinh `securitySchemes` từ trường `security` của IR (thiếu thông tin kiểu xác thực).

## 4. M3 – Đánh giá

- L5 dùng nguyên `extract_facts.extract` + `evaluate.compare` của SpecLoop-Bench; “F1 constraint bỏ type” = `compare(..., keywords = mọi từ khóa – {type})`.
- L4: so khớp trích dẫn với tài liệu đã gộp khoảng trắng (khớp nguyên văn = 100, ngược lại `rapidfuzz.partial_ratio`), ngưỡng 90. Phần tử “có căn cứ” nếu chính nó, tổ tiên hoặc hậu duệ có bằng chứng. Phiên bản nhập sẵn/sửa tay không có bằng chứng → L4 “không áp dụng”.
- Hallucination rate (xấp xỉ): fact FP mà tên tham số/thuộc tính không xuất hiện trong tài liệu / tổng fact sinh ra.

## 5. M4 – Kiểm thử

- Chế độ dự án mặc định `auto`: **full** nếu host phân giải ra IP nội bộ nằm trong `TEST_ALLOWED_NETWORKS` (sandbox), **safe** (chỉ GET/HEAD/OPTIONS) nếu là API công khai. Allowlist host rỗng ⇒ chỉ cho phép host của base URL.
- `TEST_SANDBOX_MAX_RPS`/`TEST_PUBLIC_MAX_RPS` là **trần**; cấu hình lượt chạy chỉ hạ được, không vượt. Giá trị 0 = không giới hạn (chỉ dùng trong test tự động với SUT cục bộ).
- Không theo redirect (tránh chuyển hướng sang host không được phép); chống SSRF bằng phân giải DNS rồi kiểm tra IP trước khi chạy.
- Chỉ dò tham số và **thuộc tính cấp 1** của body JSON; thuộc tính lồng nhau chỉ được kiểm qua lấy mẫu phản hồi.
- Request cơ sở: example → default → enum[0] → sinh theo kiểu/ràng buộc (có bộ sinh chuỗi từ pattern). Tham số path không tồn tại → gọi “producer” `POST` lên collection cha để lấy `id`; với `DELETE` mỗi probe dùng tài nguyên mới.
- Lặp mặc định 3 lần cho probe quyết định (bắt buộc, phụ thuộc, enum, kiểu); dừng sớm nếu kết quả lệch nhau (đánh dấu không ổn định).
- Schemathesis (tùy chọn trong prompt) **chưa tích hợp**: cờ `schemathesis` được nhận nhưng bỏ qua. Các check tương đương do chiến lược riêng đảm nhận (kiểm schema phản hồi cho mọi observation, mã trạng thái, 5xx).
- Tầng 2 khai thác thông báo lỗi bằng LLM: bật bằng `use_llm_messages: true` trong cấu hình lượt kiểm thử (cần LLM trong `.env`). Chỉ gọi khi regex không khớp; giả thuyết chỉ được tính (r = 0,6) khi trùng giá trị đã dò được bằng probe, hoặc giá trị enum gợi ý được probe xác nhận.

## 6. M5 – Phát hiện và đề xuất

- Mã sai lệch: thiếu biên → D1; cùng giá trị biên nhưng khai báo loại trừ còn thực tế bao gồm → D2 (quá chặt); khác giá trị biên → D3; khai báo biên nhưng dò tới trần không thấy → D2 (bỏ biên); phụ thuộc khai báo không được kiểm → D2; phụ thuộc mới → D9; null trong phản hồi → D8 (`nullable`); giá trị ngoài enum trong phản hồi → D5; mã trạng thái chưa khai báo → D7 thêm response (schema `$ref` tới component có cùng tập thuộc tính nếu có); 2xx khai báo không bao giờ xuất hiện còn 2xx khác thì có → D7 `move`.
- **INFO**: từ chối kèm thông báo kiểu “does not refer to an existing …/not found” (ràng buộc tham chiếu, không biểu diễn được bằng OAS). 404 của tham số path không được coi là bằng chứng ràng buộc. D0 và INFO không có đề xuất.
- `doc_conflict = true` khi finding mâu thuẫn với điều **đặc tả hiện tại đã khai báo** (đặc tả nhập sẵn được coi là tài liệu). Chính sách `prescriptive`: finding mâu thuẫn chỉ được báo cáo, không tạo đề xuất.
- Khi tham số “bắt buộc” hóa ra tùy chọn, hệ thống so phản hồi khi bỏ tham số với phản hồi của từng giá trị enum để suy `default` (ví dụ `sort` mặc định `title`).
- Nhiều đề xuất cùng sửa một danh sách (`required`, `x-dependencies`) được gộp thành cùng một patch `replace` toàn danh sách ⇒ áp dụng theo thứ tự nào cũng cho cùng kết quả.
- Kênh lấy mẫu phản hồi: cận dưới Wilson với s = n = số phản hồi thể hiện sai lệch.

## 7. M6 – Phiên bản

- Bộ áp dụng JSON Patch tự viết, chế độ “không chặt”: `add` vào khóa đã có = `replace`, `replace` khóa chưa có = `add`, `remove` khóa không tồn tại = bỏ qua (ghi cảnh báo).
- Kiểm thử hồi quy: khi chạy kiểm thử trên phiên bản tạo từ đề xuất, đề xuất được chuyển `verified` nếu không còn finding cùng (mã, pointer), ngược lại finding chuyển `reopened`.
- Vòng lặp tự động dừng khi: không còn đề xuất ≥ τ; hoặc còn đề xuất ≥ τ nhưng không cái nào tự chấp nhận được (cần người duyệt); hoặc đạt K vòng.
- Sửa tay (`POST /specs/{id}/versions`) chỉ tạo phiên bản khi validate OAS 3.0.3 sạch; patch so với cha được sinh tự động.

## 8. G5 – Thực nghiệm

- Mặc định **tắt cache LLM** khi chạy ma trận để 3 lần lặp là 3 lần gọi thật (`use_cache: true` để bật).
- C2 bỏ qua khi `test_scope: none` hoặc SUT không truy cập được (ghi rõ trong CSV/summary). API công khai chạy chế độ safe, ≤ 1 req/s.
- Wilcoxon cần ≥ 2 cặp khác 0; nếu không đủ, summary ghi “không đủ cặp”. Holm cho 2 phép so sánh (C2 vs C1, C1 vs C0); r = Z/√N với Z suy từ p hai phía; bootstrap 10.000 lần, seed 42. Chỉ số RQ3 ưu tiên GT hành vi, không có thì dùng GT tài liệu.

## 9. Bảo mật

- Secret dự án (token API, header reset) mã hóa Fernet với khóa = SHA-256(`SECRET_KEY`); API chỉ trả `has_secret`. LLM chỉ nhận nội dung tài liệu, không nhận secret. Header `Authorization`, `Cookie`, `X-Api-Key`, `X-Admin-Token`… và tên header/query của auth bị che `***` trong observation.

## 10. Chưa làm / ngoài phạm vi bản này

Tài khoản và phân quyền (FR-18), Alembic, crawl nhiều trang, tích hợp Schemathesis, chạy Playwright render trang JS, báo cáo HTML, Vitest cho từng component (đã có 1 test Playwright end-to-end). Gộp/tách phân đoạn không tự cập nhật `operation_hint` của phần mới.

- Tham số path không khai báo kiểu (thường gặp khi tài liệu không nêu) được thử với giá trị `1`.

## 11. Giao diện

- Phong cách “phần mềm doanh nghiệp”: nền xám rất nhạt, bề mặt trắng, viền mảnh, bóng nhẹ, xanh dương chủ đạo (`#0b5cd6`), xanh lá/cam/đỏ cho thành công/cảnh báo/lỗi. Khung ứng dụng: menu trái có icon (nhóm Làm việc / Hệ thống), thanh trên có breadcrumb và trạng thái API/LLM, nội dung trên nền xám với thẻ trắng. Token khai báo một chỗ (`frontend/src/theme.ts`) và bơm vào Ant Design qua `ConfigProvider` + biến CSS, nên component AntD và phần tự viết dùng chung bảng màu.
- Font IBM Plex Sans / IBM Plex Mono tự đóng gói qua `@fontsource` (có bộ ký tự tiếng Việt); không tải từ CDN để chạy offline/trong docker.
- Logo tự vẽ (SVG): vòng lặp có mũi tên ôm dấu kiểm – “vòng lặp đã kiểm chứng”; một bản React (`components/Logo.tsx`) cho thanh menu, một bản tĩnh (`public/favicon.svg`) cho tab trình duyệt. Wordmark “Spec**Loop**” với “Loop” màu chủ đạo.

## 12. Mở rộng SpecLoop-Bench lên 20 API (01/11/2026)

- Thêm 11 API theo tiêu chí README của bench (đặc tả OpenAPI 3.x chính thức, giấy phép mở, môi trường kiểm thử được, đa dạng cỡ/ràng buộc): nhóm A chạy Docker – `spring-petclinic`, `httpbin`, `typesense`, `qdrant`; nhóm B công khai chỉ đọc – `nws-weather`, `pokeapi`, `opendota`, `spaceflight-news`, `jikan`, `postcodes-io`, `wikimedia-rest`. Tổng 877 operation / 61 793 facts (bản 9 API: 221 / 21 650).
- Loại các ứng viên cần khóa/OAuth (Spotify, YouTube, TMDB), đặc tả nhiều tệp `$ref` ngoài (Shlink, Open Food Facts), xác thực Basic mà bộ thăm dò chưa hỗ trợ (Gotify, Listmonk), hoặc chặn bot (Art Institute of Chicago).
- Viết `tools/swagger2_to_oas3.py` (Python thuần) thay cho `npx swagger2openapi` để chuyển httpbin; các lỗi hợp lệ hay gặp ở đặc tả tự sinh (kiểu `int/float`, số/boolean dạng chuỗi, regex `\p{L}`, thiếu tham số path, trường lạ trong `info.contact`, từ khóa JSON Schema 2020-12) được sửa tối thiểu và ghi từng mục vào `source.normalization`.
- Qdrant ánh xạ cổng 6343:6333 vì 6333 hay bị Qdrant khác trên máy chiếm; Typesense dùng khóa cố định `specloop` (biến `TYPESENSE_API_KEY`). GT hành vi của 11 API mới để `pending` – xác minh dần qua kiểm thử.

## 13. Người dùng tự thêm API vào bộ dữ liệu (03/11/2026)

- Trang *Bộ dữ liệu* + `/api/v1/bench/*` (`services/bench_admin.py`) gọi lại chính công cụ của bench: logic nhập API tách thành `tools/spec_import.py` (đọc YAML/JSON, Swagger 2.0 → 3.0, hạ cấp 3.1, sửa lỗi hay gặp, gợi ý meta, tạo/xóa thư mục); `build_dataset.update_manifest(root, apis)` và `validate_dataset.check_api(..., root)` nhận thư mục gốc làm tham số. `add_api.py` (CLI) dùng cùng module nên hai đường cho kết quả giống nhau.
- Có bước *xem trước* không ghi gì; tạo chỉ ghi khi đặc tả hợp lệ OAS 3.0.3 sau khi tự sửa, lỗi giữa chừng thì xóa thư mục và dựng lại manifest. Các thao tác ghi tuần tự hóa bằng một khóa (cùng sửa `manifest.json`/`stats.csv`).
- Khóa API không bao giờ lưu: form chỉ nhận *tên biến môi trường* (`env_var`), giống quy ước của bench.
- Chỉ xóa được API có `added_via: web` để không lỡ tay xóa API gốc. Đọc tệp chỉ cho phép tệp nằm trong `apis/<id>/` (chặn `../`), tối đa 3 MB; đặc tả tải từ URL tối đa 20 MB, timeout 60 s, chỉ http/https. Cho phép URL nội bộ (localhost) vì đặc tả của API chạy Docker thường nằm ở đó – công cụ dùng cục bộ cho nhóm nghiên cứu.
- Docker: `./SpecLoop-Bench` gắn vào container backend thành volume để API thêm từ web không mất khi tạo lại container.
- Sửa kèm: `build_dataset` ghi khóa tệp trong `manifest.json` bằng `/` (trước đó build trên Windows ra `\`); mã API gợi ý bỏ dấu tiếng Việt (“Kho Sách Thử” → `kho-sach-thu`).
- Tổng quan dùng thẻ KPI có icon, `Steps` 5 bước của vòng lặp, biểu đồ sai lệch theo mã và bảng dự án gần đây; danh sách dự án là bảng dữ liệu có tìm kiếm; chi tiết dự án có đầu trang (tên, chip cấu hình, chọn phiên bản) và tab có icon. Monaco dùng theme sáng cùng bảng màu; Swagger UI dùng nguyên bản sáng.
- Bảng rộng hơn cột thì cuộn ngang bên trong (`.ant-table-content { overflow-x: auto }`) để không tràn đè lên cột bên cạnh. Mọi `data-testid` và nhãn mà e2e Playwright dựa vào được giữ nguyên khi làm lại giao diện.
