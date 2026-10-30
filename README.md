# SpecLoop

Hệ thống web sinh đặc tả **OpenAPI 3.0.3** từ tài liệu REST API bằng LLM, đánh giá đặc tả, **kiểm thử API thật** để thu
phản hồi, rồi phát hiện và tinh chỉnh các ràng buộc sai (đề xuất JSON Patch kèm bằng chứng + độ tin cậy, người dùng duyệt).

```
Tài liệu → OAS v0 → Đánh giá → Kiểm thử → Phát hiện sai lệch (D0–D9) → Đề xuất → OAS v(k+1) → kiểm thử lại … hội tụ
```

- Backend: Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 + SQLite · job nền trong tiến trình + SSE.
- Frontend: React 18 · TypeScript · Vite · Ant Design 5 (theme tùy biến kiểu phần mềm doanh nghiệp) · TanStack Query ·
  Monaco · Swagger UI · Recharts. Giao diện tiếng Việt; font IBM Plex Sans/Mono tự đóng gói (có bộ ký tự tiếng Việt),
  không tải gì từ CDN.
- LLM: một adapter OpenAI-compatible (OpenAI, Gemini, Ollama, LM Studio) + `FakeLLM` cho test/offline.
- Bộ dữ liệu: `SpecLoop-Bench/` (dùng lại `tools/oas_utils.py`, `extract_facts.py`, `evaluate.py` bằng import).

Tài liệu kỹ thuật đầy đủ: [docs/TECH_SPEC.md](docs/TECH_SPEC.md). Các quyết định khi đặc tả chưa rõ: [DECISIONS.md](DECISIONS.md).

## Cấu trúc

```
specloop/
  backend/app/          main.py, config.py, db.py, models.py, jobs.py, security.py, bench.py, experiments.py (CLI)
  backend/app/api/v1/   projects, specs (sinh/nhập/đánh giá/diff/xuất), testing (test-runs/findings/proposals), jobs, misc
  backend/app/services/ ingestion · generation · evaluation · testing · analysis · versioning · llm · experiments
  backend/tests/        test_unit.py (thuật toán lõi) · test_integration.py (vòng lặp đầy đủ với Bookstore-Lab)
  frontend/             ứng dụng React (src/api, pages, components, hooks) + e2e Playwright
  SpecLoop-Bench/       bộ dữ liệu + API thử nghiệm Bookstore-Lab (13 sai lệch cài cắm)
  docs/ docker-compose.yml .env.example DECISIONS.md
```

## 1. Chạy nhanh bằng Docker

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env   (điền LLM nếu muốn)
docker compose up --build
```

| Dịch vụ | Địa chỉ |
|---|---|
| Giao diện | http://localhost:3000 |
| Backend API (+ Swagger của backend) | http://localhost:8001/api/v1 · http://localhost:8001/docs |
| Bookstore-Lab (SUT) | http://localhost:8000/v1 — trong mạng docker: `http://bookstore-lab:8000/v1` |

Khi tạo dự án Bookstore-Lab trong giao diện chạy bằng docker, dùng base URL `http://bookstore-lab:8000/v1`, reset
`POST /__admin/reset` với header `X-Admin-Token: reset-me`. Ollama trên máy host: `LLM_BASE_URL=http://host.docker.internal:11434/v1`.

## 2. Chạy thủ công (phát triển)

Yêu cầu: Python 3.11, Node.js ≥ 20.

### Windows (PowerShell)

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8001 --reload

# Bookstore-Lab (cửa sổ khác)
cd SpecLoop-Bench\apis\bookstore-lab\sut
..\..\..\..\backend\.venv\Scripts\python -m uvicorn app:app --port 8000

# Frontend (cửa sổ khác) – Vite proxy /api → http://localhost:8001
cd frontend
npm install
npm run dev          # http://localhost:5173
```

### Linux / macOS (bash)

```bash
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8001 --reload &
(cd ../SpecLoop-Bench/apis/bookstore-lab/sut && ../../../../backend/.venv/bin/uvicorn app:app --port 8000 &)
cd ../frontend && npm install && npm run dev
```

Backend đọc `.env` ở thư mục gốc `specloop/` (hoặc thư mục đang chạy). CSDL mặc định: `data/specloop.db`.

## 3. Cấu hình LLM

Sao chép `.env.example` thành `.env` và bỏ chú thích **một** khối:

| Nhà cung cấp | LLM_BASE_URL | LLM_MODEL (ví dụ) |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Gemini (OpenAI-compatible) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash` |
| Ollama | `http://localhost:11434/v1` | `qwen2.5:7b-instruct` |
| LM Studio | `http://localhost:1234/v1` | tên mô hình đang nạp |

Không có LLM vẫn dùng được toàn bộ hệ thống với mô hình `fake` (trích xuất theo luật). Trang **Cài đặt LLM** có nút thử
kết nối; mọi lời gọi được ghi vào bảng `llm_call` (mô hình, token vào/ra, độ trễ, cache hit). Khóa API không được lưu
trong CSDL, không ghi log.

## 4. Luồng sử dụng

1. **Tạo dự án** (base URL, xác thực, lệnh reset sandbox) → **Tài liệu**: tải tệp HTML/MD/PDF/TXT, nhập URL hoặc dán văn bản;
   kiểm tra/gộp/tách phân đoạn.
2. **Đặc tả** → *Sinh đặc tả* (chọn mô hình) – job nền, tiến trình qua SSE. Kết quả: phiên bản `generated` và `repaired`.
   Trình xem 3 khung: tài liệu (làm nổi bật trích dẫn) · YAML · Swagger UI. Hoặc *Nhập OAS* có sẵn.
3. **Đánh giá**: tải ground truth (tài liệu/hành vi) → P/R/F1 theo nhóm fact, L1–L4, lint.
4. **Kiểm thử**: cấu hình (chế độ auto/safe/full, ngân sách, tốc độ) → theo dõi theo operation, bảng observation.
5. **Sai lệch & đề xuất**: xem bằng chứng tài liệu + runtime, JSON Patch, YAML trước/sau → Chấp nhận/Từ chối/Sửa,
   chấp nhận hàng loạt theo ngưỡng → *Áp dụng* tạo phiên bản `refined-k`; hoặc *Vòng lặp tự động* (K = 3).
6. **Phiên bản**: diff YAML (Monaco) + diff ngữ nghĩa theo operation; xuất YAML/JSON (tùy chọn bỏ `x-*`, kèm `x-evidence`).

An toàn kiểm thử: chỉ gọi host được phép, chặn IP nội bộ ngoài `TEST_ALLOWED_NETWORKS`, ≤ 5 req/s (sandbox) / ≤ 1 req/s
(công khai), ngân sách 150/30 request mỗi operation, timeout 10 s, API công khai mặc định chỉ GET/HEAD/OPTIONS, header
xác thực bị che trong vết.

## 5. Kiểm thử tự động

```bash
cd backend
.venv/Scripts/python -m pytest          # Linux: .venv/bin/python -m pytest
.venv/Scripts/ruff check app tests
cd ../frontend && npm run build && npm run lint
npx playwright install chromium     # lần đầu
npx playwright test                 # e2e: tạo dự án → nạp → sinh → kiểm thử → duyệt → phiên bản → diff
```

Playwright tự khởi động Bookstore-Lab (8000), backend (8001, CSDL SQLite tạm) và Vite (5173); cần đã tạo `backend/.venv`.
Nếu đang chạy `docker compose`, hãy `docker compose down` trước để giải phóng các cổng.

`test_integration.py` tự khởi động Bookstore-Lab bằng uvicorn và kiểm tra đúng các tiêu chí nghiệm thu: nhập GT tài liệu làm
v0 → kiểm thử → phủ ≥ 12/13 sai lệch (BS-13 là D0, chỉ báo cáo) → chấp nhận mọi đề xuất → v1 → F1 ràng buộc (bỏ `type`)
so với GT hành vi ≥ 0,95, không có fact FP → kiểm thử lại v1 không còn đề xuất mới; FakeLLM sinh OAS 3.0.3 hợp lệ từ
`docs/original.md`, mọi phần tử có bằng chứng; vòng lặp tự động + SSE; thực nghiệm C0/C1/C2.

## 6. Thực nghiệm (G5)

```bash
cd backend
.venv/Scripts/python -m app.experiments --config experiments.example.yaml
```

Đọc `SpecLoop-Bench/apis/*/meta.yaml`, chạy ma trận API × mô hình × C0/C1/C2 × số lần lặp, xuất `data/experiments/<tên>/results.csv`,
`summary.md` (trung vị theo API, macro, Wilcoxon C2 vs C1 và C1 vs C0 có hiệu chỉnh Holm, r = Z/√N, KTC bootstrap 95%).
Cũng chạy được từ trang **Thực nghiệm** hoặc `POST /api/v1/experiments`.

## 7. Kết quả đo được (chạy thật, 30/10/2026)

### Bookstore-Lab – vòng phản hồi kiểm thử (v0 = GT tài liệu nhập sẵn)

| Chỉ số | Giá trị |
|---|---|
| F1 ràng buộc (bỏ `type`) của GT tài liệu so với GT hành vi | 0,812 (P 0,857 · R 0,771) |
| Request lượt kiểm thử v0 | 363 (8 operation, ngân sách 150/operation) |
| Finding | 18: D1 × 5, D7 × 3, D2 × 2, D5 × 2, D4, D8, D9, D0, INFO × 2 |
| Sai lệch cài cắm được phát hiện | **13/13** (BS-13 → D0, chỉ báo cáo) |
| Đề xuất | 15 (7 tự chấp nhận được ≥ 0,8, 6 cần duyệt, 2 gợi ý) |
| F1 ràng buộc v1 so với GT hành vi | **1,000** (109/109, FP = 0) · F1 micro mọi fact 1,000 |
| Kiểm thử lại v1 | 316 request, chỉ còn D0 + INFO → hội tụ |

### Sinh OAS bằng FakeLLM (baseline theo luật, 1 lần chạy – kết quả xác định)

| API | Cấu hình | F1 (GT tài liệu) | F1 ràng buộc (GT tài liệu) | F1 ràng buộc (GT hành vi) | Request |
|---|---|---:|---:|---:|---:|
| bookstore-lab | C0 / C1 | 0,795 | 0,600 | 0,450 | 0 |
| bookstore-lab | C2 | 0,783 | 0,571 | **0,519** | 615 |
| petstore3 (rendered.md) | C0 / C1 | 0,354 / 0,401 | 0,266 | – | 0 |
| language-tool (rendered.md) | C0 / C1 | 0,735 / 0,714 | 0,200 | – | 0 |

FakeLLM chỉ là baseline; các số trên không đại diện cho LLM thật.

### LLM thật (tiêu chí nghiệm thu 4) – Qwen3 qua Ollama, máy RTX 3050 Laptop 4 GB

Một lần chạy, nhiệt độ 0, tài liệu `original.md` (Bookstore-Lab) và `rendered.md` (Petstore). F1 so với **GT tài liệu**;
F1 ràng buộc không tính từ khóa `type`. Petstore không có SUT chạy cục bộ nên không có C2.

| API | Mô hình | Cấu hình | Hợp lệ OAS 3.0.3 | Operation | P | R | **F1** | F1 ràng buộc (tài liệu) | F1 ràng buộc (hành vi) | Thời gian sinh |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| bookstore-lab | qwen3:8b (lai CPU/GPU) | C0 / C1 | có | 8/8 | 0,988 | 0,558 | **0,713** | 0,571 | 0,517 | ≈ 27 phút |
| bookstore-lab | qwen3:8b | C2 (287 request, 2 vòng) | có | 8/8 | 0,988 | 0,568 | **0,722** | 0,601 | 0,545 | + 70 s |
| bookstore-lab | qwen3-4b-gpu (100% GPU) | C1 | có | 8/8 | 0,899 | 0,281 | **0,428** | 0,269 | 0,215 | ≈ 1,5 phút |
| petstore3 | qwen3-4b-gpu (100% GPU) | C1 | có | 19/19 | 0,720 | 0,557 | **0,628** | 0,223 | – | ≈ 3,5 phút |

Nhận xét: bản 8B chính xác hơn nhiều (P ≈ 0,99) nhưng không vừa VRAM 4 GB nên 61% chạy trên CPU; bản 4B chạy trọn trên
GPU, nhanh hơn ~15 lần nhưng bỏ sót nhiều thuộc tính body/response. Petstore chưa chạy với 8B (≈ 80 phút, đẩy CPU kín).
Kết quả chi tiết: `data/experiments/qwen3-8b-bookstore/`, `data/experiments/qwen3-4b-gpu/`.

#### Chạy Ollama trên GPU nhỏ (đã kiểm chứng trên RTX 3050 4 GB)

1. Qwen3 là mô hình suy luận: **bắt buộc** `LLM_REASONING_EFFORT=none`, nếu không mỗi lời gọi sinh ~15.000 ký tự
   “suy nghĩ” (470 s thay vì 7 s).
2. `LLM_STRUCTURED_OUTPUT=true` ép đầu ra theo JSON Schema của OperationIR – mô hình 4B luôn trả JSON hợp lệ.
3. Để mô hình nằm trọn trong GPU: đặt biến môi trường `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, khởi động
   lại Ollama, rồi `ollama create qwen3-4b-gpu -f ollama/Modelfile.qwen3-4b-gpu` (ép mọi lớp lên GPU, ngữ cảnh 4096).
   Kiểm tra bằng `ollama ps` → cột PROCESSOR phải là `100% GPU`.
4. `.env` mẫu cho máy này:

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3-4b-gpu          # hoặc qwen3:8b nếu chấp nhận chậm và tốn CPU
LLM_REASONING_EFFORT=none
LLM_STRUCTURED_OUTPUT=true
LLM_MAX_CONCURRENCY=1
LLM_TIMEOUT_S=300
DOCKER_LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Chạy lại thực nghiệm: `cd backend && .venv/Scripts/python -m app.experiments --config experiments.qwen-gpu.yaml`
(hoặc `experiments.qwen.yaml` cho qwen3:8b).

## 8. API backend (tóm tắt, tiền tố `/api/v1`)

Tác vụ dài trả `202 {job_id}`; theo dõi `GET /jobs/{id}` hoặc SSE `GET /jobs/{id}/events`. Lỗi theo RFC 7807
(`application/problem+json`). Danh sách đầy đủ: http://localhost:8001/docs.

`POST/GET /projects` · `GET/PATCH/DELETE /projects/{id}` · `POST /projects/{id}/documents` · `GET /documents/{id}/chunks` ·
`PATCH /chunks/{id}` · `POST /documents/{id}/chunks/merge` · `POST /chunks/{id}/split` · `POST /projects/{id}/generate` ·
`POST /projects/{id}/specs/import` · `GET /projects/{id}/specs` · `GET /specs/{id}?format=yaml|json` · `POST /specs/{id}/versions` ·
`GET /specs/{id}/evidence?pointer=` · `POST /specs/{id}/validate` · `POST /projects/{id}/ground-truths` ·
`POST /specs/{id}/evaluations` · `GET /evaluations/{id}` · `POST /specs/{id}/test-runs` · `GET /test-runs/{id}` ·
`GET /test-runs/{id}/observations` · `POST /test-runs/{id}/cancel` · `GET /test-runs/{id}/findings` · `GET /findings/{id}` ·
`GET /specs/{id}/proposals?status=` · `POST /proposals/{id}/accept|reject` · `PATCH /proposals/{id}` ·
`POST /specs/{id}/proposals/accept-threshold` · `POST /specs/{id}/apply` · `POST /specs/{id}/refine-loop` ·
`GET /specs/{id}/diff?against=` · `GET /specs/{id}/export?format=&strip_extensions=` · `GET /jobs/{id}` · `GET /jobs/{id}/events` ·
`POST /experiments` · `GET /experiments/{id}/results` · `GET /llm/providers` · `POST /llm/test` · `GET /dashboard` · `GET /health`
