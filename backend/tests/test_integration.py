"""Kiểm thử tích hợp qua REST API – tiêu chí nghiệm thu 2 và 3, G2, G5 (không cần LLM thật)."""
from __future__ import annotations

import json

import pytest

from app.bench import oas_utils
from tests.conftest import BOOKSTORE, wait_job

GT_DOC = (BOOKSTORE / "ground_truth" / "openapi.yaml").read_text(encoding="utf-8")
GT_BEHAVIOR = (BOOKSTORE / "ground_truth" / "behavior_openapi.yaml").read_text(encoding="utf-8")
DISCREPANCIES = json.loads((BOOKSTORE / "ground_truth" / "discrepancies.json").read_text(encoding="utf-8"))
DOC_MD = (BOOKSTORE / "docs" / "original.md").read_text(encoding="utf-8")


def new_project(client, sut=None, name="Bookstore-Lab"):
    body = {"name": name}
    if sut:
        body.update({"base_url": sut["base_url"], "reset": {"method": "POST", "url": "/__admin/reset"},
                     "reset_headers": {"X-Admin-Token": "reset-me"}})
    r = client.post("/api/v1/projects", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert client.get("/health").json() == {"status": "ok"}


def test_problem_json(client):
    r = client.get("/api/v1/projects/999999")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 404


def test_secret_never_returned(client):
    p = client.post("/api/v1/projects", json={"name": "s", "auth": {"type": "bearer"},
                                               "auth_secret": "tok-super-secret"}).json()
    assert p["has_secret"] is True
    assert "tok-super-secret" not in json.dumps(p)
    assert "tok-super-secret" not in client.get(f"/api/v1/projects/{p['id']}").text


# ------------------------------------------------------------------ tiêu chí 3: M2 với FakeLLM
def test_generate_with_fake_llm(client):
    p = new_project(client, name="Sinh bằng FakeLLM")
    doc = client.post(f"/api/v1/projects/{p['id']}/documents", json={"text": DOC_MD, "filename": "original.md"})
    assert doc.status_code == 201, doc.text
    chunks = client.get(f"/api/v1/documents/{doc.json()['id']}/chunks").json()
    hints = {f"{c['operation_hint']['method']} {c['operation_hint']['path']}" for c in chunks if c["operation_hint"]}
    assert len(hints) == 8
    r = client.post(f"/api/v1/projects/{p['id']}/generate", json={"model": "fake"})
    assert r.status_code == 202
    job = wait_job(client, r.json()["job_id"])
    assert job["status"] == "succeeded", job
    vid = job["result"]["version_id"]
    spec = client.get(f"/api/v1/specs/{vid}").json()["content"]
    assert spec["openapi"] == "3.0.3" and len(spec["paths"]) == 6
    assert sum(len(item) for item in spec["paths"].values()) == 8
    rep = client.post(f"/api/v1/specs/{vid}/validate").json()
    assert rep["L2_valid"]["ok"], rep["L2_valid"]
    g = rep["L4_grounding"]
    assert g["applicable"] and g["elements_without_evidence_count"] == 0, g["elements_without_evidence"]
    assert g["grounded_rate"] == 1.0
    ev = client.get(f"/api/v1/specs/{vid}/evidence", params={"pointer": "/paths/~1books/get/parameters/0"}).json()
    assert ev and "limit" in ev[0]["quote"]
    # gọi LLM được ghi vào llm_call
    assert client.get("/api/v1/llm/usage").json()[0]["calls"] >= 8


def test_chunk_merge_split(client):
    p = new_project(client, name="Phân đoạn")
    doc = client.post(f"/api/v1/projects/{p['id']}/documents", json={"text": DOC_MD}).json()
    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    merged = client.post(f"/api/v1/documents/{doc['id']}/chunks/merge",
                         json={"chunk_ids": [chunks[1]["id"], chunks[2]["id"]]}).json()
    assert len(merged) == len(chunks) - 1
    split = client.post(f"/api/v1/chunks/{merged[1]['id']}/split", json={"offset": 5}).json()
    assert len(split) == len(chunks)
    upd = client.patch(f"/api/v1/chunks/{split[0]['id']}", json={"is_global": True}).json()
    assert upd["is_global"] is True


# ------------------------------------------------------------------ G2: đánh giá
def test_evaluation_doc_gt_vs_behavior(client):
    p = new_project(client, name="Đánh giá")
    v = client.post(f"/api/v1/projects/{p['id']}/specs/import", json={"text": GT_DOC}).json()
    gt = client.post(f"/api/v1/projects/{p['id']}/ground-truths", json={"kind": "behavior", "text": GT_BEHAVIOR})
    assert gt.status_code == 201
    r = client.post(f"/api/v1/specs/{v['id']}/evaluations", json={"ground_truth_id": gt.json()["id"]})
    assert r.status_code == 202
    assert wait_job(client, r.json()["job_id"])["status"] == "succeeded"
    ev = client.get(r.json()["resource_url"].replace("/api/v1", "/api/v1", 1)).json()
    c = ev["metrics"]["L5"]["constraint_no_type"]
    assert c["f1"] == pytest.approx(0.81, abs=0.02)
    assert ev["metrics"]["static"]["L2_valid"]["ok"]


# ------------------------------------------------------------------ tiêu chí 2: vòng lặp đầy đủ với Bookstore-Lab
def _matches(d, findings):
    ops = [o.strip().split(" (")[0] for o in d["op"].split(",")]
    for f in findings:
        if f["code"] != d["code"] or not any(f["operation_id"] == o or (d["location"].startswith("resp") and
                                                                         f["operation_id"] in d["op"]) for o in ops):
            continue
        loc = d["location"]
        if loc == "responses":
            if f["location"] == "responses" and f["keyword"] in d["keyword"]:
                return True
        elif loc.startswith("resp"):
            if f["location"].startswith("resp") and loc.split(":")[1] in f["location"]:
                return True
        elif f["location"] == loc:
            return True
    return False


def run_tests(client, spec_id, base_url):
    r = client.post(f"/api/v1/specs/{spec_id}/test-runs", json={"base_url": base_url})
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job_id"])
    assert job["status"] == "succeeded", job
    run_id = r.json()["resource_id"]
    run = client.get(f"/api/v1/test-runs/{run_id}").json()
    assert run["status"] == "succeeded"
    return run_id, run


def test_bookstore_full_loop(client, sut):
    p = new_project(client, sut)
    v0 = client.post(f"/api/v1/projects/{p['id']}/specs/import", json={"text": GT_DOC}).json()
    run_id, run = run_tests(client, v0["id"], sut["base_url"])
    assert run["stats"]["reset"]["done"] is True
    assert run["stats"]["requests"] <= 150 * 8
    findings = client.get(f"/api/v1/test-runs/{run_id}/findings").json()
    covered = [d["id"] for d in DISCREPANCIES["discrepancies"] if _matches(d, findings)]
    assert len(covered) >= 12, f"chỉ phủ {covered}"
    d0 = [f for f in findings if f["code"] == "D0"]
    assert any(f["operation_id"] == "GET /authors" and f["location"] == "query:page" for f in d0)
    assert all(not f["proposal_ids"] for f in findings if f["code"] in ("D0", "INFO"))
    # observation được lưu, header nhạy cảm bị che
    obs = client.get(f"/api/v1/test-runs/{run_id}/observations", params={"size": 5}).json()
    assert obs["total"] == run["stats"]["requests"] and obs["items"]
    # chi tiết finding có observation hỗ trợ
    fd = client.get(f"/api/v1/findings/{findings[0]['id']}").json()
    assert fd["observations"]
    # chấp nhận toàn bộ đề xuất có patch → v1
    props = client.get(f"/api/v1/specs/{v0['id']}/proposals", params={"status": "pending"}).json()
    assert props and all(pp["json_patch"] for pp in props)
    for pp in props:
        assert client.post(f"/api/v1/proposals/{pp['id']}/accept").json()["status"] == "accepted"
    v1 = client.post(f"/api/v1/specs/{v0['id']}/apply", json={}).json()
    assert v1["label"] == "refined-1" and v1["parent_id"] == v0["id"]
    # đánh giá v1 với GT hành vi
    gt = client.post(f"/api/v1/projects/{p['id']}/ground-truths", json={"kind": "behavior", "text": GT_BEHAVIOR})
    r = client.post(f"/api/v1/specs/{v1['id']}/evaluations", json={"ground_truth_id": gt.json()["id"]})
    wait_job(client, r.json()["job_id"])
    ev = client.get(f"/api/v1/evaluations/{r.json()['resource_id']}").json()
    assert ev["metrics"]["L5"]["constraint_no_type"]["f1"] >= 0.95
    assert ev["facts"]["fp"] == [] and ev["facts"]["wrong_value"] == []
    # diff + xuất
    diff = client.get(f"/api/v1/specs/{v1['id']}/diff").json()
    assert diff["semantic"]["changes"] > 0 and "maximum: 100" in diff["text_diff"]
    exported = client.get(f"/api/v1/specs/{v1['id']}/export", params={"format": "yaml", "strip_extensions": True})
    assert "x-dependencies" not in exported.text and oas_utils.normalize_to_303(
        __import__("yaml").safe_load(exported.text))
    # chạy lại trên v1: không còn đề xuất mới ngoài D0/INFO; đề xuất cũ được xác minh (hồi quy)
    run2_id, _ = run_tests(client, v1["id"], sut["base_url"])
    f2 = client.get(f"/api/v1/test-runs/{run2_id}/findings").json()
    assert {f["code"] for f in f2} <= {"D0", "INFO"}, [(f["code"], f["summary"]) for f in f2]
    assert client.get(f"/api/v1/specs/{v1['id']}/proposals").json() == []
    verified = client.get(f"/api/v1/specs/{v0['id']}/proposals", params={"status": "verified"}).json()
    assert len(verified) == len(props)


def test_sse_and_refine_loop(client, sut):
    p = new_project(client, sut, name="Vòng lặp tự động")
    v0 = client.post(f"/api/v1/projects/{p['id']}/specs/import", json={"text": GT_DOC}).json()
    r = client.post(f"/api/v1/specs/{v0['id']}/refine-loop",
                    json={"max_iter": 3, "test_config": {"base_url": sut["base_url"]}})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as s:
        events = [line for line in s.iter_lines() if line.startswith("event:")]
    assert events[-1] == "event: finished" and "event: progress" in events
    job = wait_job(client, job_id)
    assert job["status"] == "succeeded", job
    res = job["result"]
    assert res["iterations"][0]["auto_accepted"]  # các đề xuất ≥ 0,8 không mâu thuẫn tài liệu
    assert res["final_spec_id"] != v0["id"]
    # đề xuất mâu thuẫn tài liệu không bao giờ được tự chấp nhận
    conflicts = client.get(f"/api/v1/specs/{v0['id']}/proposals").json()
    assert all(pp["status"] == "pending" for pp in conflicts if pp["doc_conflict"])


def test_proposal_edit_reject_and_threshold(client, sut):
    p = new_project(client, sut, name="Duyệt đề xuất")
    v0 = client.post(f"/api/v1/projects/{p['id']}/specs/import", json={"text": GT_DOC}).json()
    run_tests(client, v0["id"], sut["base_url"])
    props = client.get(f"/api/v1/specs/{v0['id']}/proposals").json()
    first = props[0]
    rej = client.post(f"/api/v1/proposals/{first['id']}/reject").json()
    assert rej["status"] == "rejected"
    edited = client.patch(f"/api/v1/proposals/{props[1]['id']}",
                          json={"json_patch": [{"op": "add", "path": "/info/x-note", "value": "sửa tay"}]}).json()
    assert edited["status"] == "edited"
    acc = client.post(f"/api/v1/specs/{v0['id']}/proposals/accept-threshold", params={"threshold": 0.8}).json()
    assert all(a["confidence"] >= 0.8 and not a["doc_conflict"] for a in acc)
    v1 = client.post(f"/api/v1/specs/{v0['id']}/apply", json={}).json()
    assert v1["content"]["info"]["x-note"] == "sửa tay"
    bad = client.patch(f"/api/v1/proposals/{props[2]['id']}", json={"json_patch": [{"op": "nope"}]})
    assert bad.status_code in (409, 422)


def test_manual_version_requires_valid_spec(client):
    p = new_project(client, name="Sửa tay")
    v0 = client.post(f"/api/v1/projects/{p['id']}/specs/import", json={"text": GT_DOC}).json()
    bad = client.post(f"/api/v1/specs/{v0['id']}/versions", json={"content": {"openapi": "3.0.3", "paths": {
        "/x": {"get": {"responses": {"200": {}}}}}}})
    assert bad.status_code == 422
    content = v0["content"]
    content["info"]["title"] = "Đã sửa"
    ok = client.post(f"/api/v1/specs/{v0['id']}/versions", json={"content": content}).json()
    assert ok["label"] == "manual" and ok["patch_from_parent"]


# ------------------------------------------------------------------ G5: thực nghiệm
def test_experiment_matrix(client, sut):
    r = client.post("/api/v1/experiments", json={"name": "tn-test", "apis": ["bookstore-lab"], "models": ["fake"],
                                                  "configs": ["C0", "C1", "C2"], "repeats": 1,
                                                  "base_url_overrides": {"bookstore-lab": sut["base_url"]}})
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job_id"])
    assert job["status"] == "succeeded", job
    res = client.get(r.json()["resource_url"]).json()
    rows = {row["config"]: row for row in res["rows"]}
    assert set(rows) == {"C0", "C1", "C2"}
    assert all(row["status"] == "ok" for row in rows.values()), rows
    assert rows["C2"]["requests"] > 0
    assert rows["C2"]["constraint_f1_behavior"] >= rows["C1"]["constraint_f1_behavior"]
    csv_text = client.get(r.json()["resource_url"], params={"format": "csv"}).text
    assert csv_text.startswith("api,model,config")
    assert "Wilcoxon" in client.get(r.json()["resource_url"], params={"format": "md"}).text
