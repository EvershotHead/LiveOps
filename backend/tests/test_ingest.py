"""导入器测试：四格式 roundtrip、损坏文件、空数据、映射、超长标记、最少字段。"""

import json

import pytest

from liveops.ingest import (
    EmptyDataError,
    FileReadError,
    apply_mapping,
    project_rows,
    read_file,
    suggest_mapping,
    validate_posts,
)


@pytest.fixture
def sample_rows():
    return [
        {"text": "这版本地图真不错", "published_at": "2026-07-02 10:00:00",
         "source_url": "https://www.bilibili.com/video/BV1", "likes": "12", "rpid": "100"},
        {"text": "抽卡又歪了", "published_at": "2026-07-03 11:30:00",
         "source_url": "https://www.bilibili.com/video/BV1", "likes": "5", "rpid": "101"},
    ]


class TestReaders:
    def test_csv_roundtrip(self, tmp_path, sample_rows):
        import csv
        p = tmp_path / "c.csv"
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(sample_rows[0].keys()))
            w.writeheader()
            w.writerows(sample_rows)
        t = read_file(p)
        assert t.format == "csv"
        assert t.row_count == 2
        assert t.rows[0]["text"] == "这版本地图真不错"

    def test_gbk_csv(self, tmp_path, sample_rows):
        import csv, io
        p = tmp_path / "gbk.csv"
        with open(p, "w", newline="", encoding="gbk") as f:
            w = csv.DictWriter(f, fieldnames=list(sample_rows[0].keys()))
            w.writeheader()
            w.writerows(sample_rows)
        t = read_file(p)
        assert t.row_count == 2

    def test_jsonl_roundtrip(self, tmp_path, sample_rows):
        p = tmp_path / "d.jsonl"
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in sample_rows), encoding="utf-8")
        t = read_file(p)
        assert t.format == "jsonl" and t.row_count == 2

    def test_jsonl_with_bad_lines(self, tmp_path, sample_rows):
        p = tmp_path / "bad.jsonl"
        lines = [json.dumps(sample_rows[0]), "{broken json", json.dumps(sample_rows[1])]
        p.write_text("\n".join(lines), encoding="utf-8")
        t = read_file(p)
        assert t.row_count == 2
        assert any("跳过" in w for w in t.warnings)

    def test_json_array(self, tmp_path, sample_rows):
        p = tmp_path / "a.json"
        p.write_text(json.dumps(sample_rows, ensure_ascii=False), encoding="utf-8")
        t = read_file(p)
        assert t.format == "json" and t.row_count == 2

    def test_json_with_data_key(self, tmp_path, sample_rows):
        p = tmp_path / "w.json"
        p.write_text(json.dumps({"data": sample_rows}), encoding="utf-8")
        assert read_file(p).row_count == 2

    def test_xlsx_roundtrip(self, tmp_path, sample_rows):
        import openpyxl
        p = tmp_path / "x.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(list(sample_rows[0].keys()))
        for r in sample_rows:
            ws.append(list(r.values()))
        wb.save(p)
        t = read_file(p)
        assert t.format == "xlsx" and t.row_count == 2
        assert t.rows[1]["text"] == "抽卡又歪了"

    def test_corrupted_xlsx(self, tmp_path):
        p = tmp_path / "broken.xlsx"
        p.write_bytes(b"PK\x03\x04 not really a zip")
        with pytest.raises(FileReadError):
            read_file(p)

    def test_truncated_csv_still_reports(self, tmp_path):
        p = tmp_path / "t.csv"
        p.write_text("text,published_at,source_url\n\"unclosed quote,2026", encoding="utf-8")
        # csv 模块容错，只要能解析出数据行就不抛
        t = read_file(p)
        assert t.row_count >= 1

    def test_empty_file(self, tmp_path):
        p = tmp_path / "e.csv"
        p.write_text("", encoding="utf-8")
        with pytest.raises((EmptyDataError, FileReadError)):
            read_file(p)

    def test_header_only_csv(self, tmp_path):
        p = tmp_path / "h.csv"
        p.write_text("text,published_at,source_url\n", encoding="utf-8")
        with pytest.raises(EmptyDataError):
            read_file(p)

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileReadError):
            read_file(tmp_path / "nope.csv")

    def test_unsupported_format(self, tmp_path):
        p = tmp_path / "x.parquet"
        p.write_bytes(b"whatever")
        from liveops.ingest import UnsupportedFormatError
        with pytest.raises(UnsupportedFormatError):
            read_file(p)


class TestMapping:
    def test_suggest_by_alias(self, tmp_path, sample_rows):
        import csv
        p = tmp_path / "m.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["评论内容", "评论时间", "视频链接", "点赞", "rpid"])
            w.writeheader()
            for r in sample_rows:
                w.writerow({"评论内容": r["text"], "评论时间": r["published_at"],
                            "视频链接": r["source_url"], "点赞": r["likes"], "rpid": r["rpid"]})
        t = read_file(p)
        s = suggest_mapping(t)
        assert s["text"] == "评论内容"
        assert s["published_at"] == "评论时间"
        assert s["source_url"] == "视频链接"
        assert s["likes"] == "点赞"

    def test_apply_mapping_missing_required(self):
        r = apply_mapping(None, {"text": "a", "published_at": None, "source_url": None})  # type: ignore
        assert r.missing_required == ["published_at", "source_url"]

    def test_project_rows(self, tmp_path, sample_rows):
        import csv
        p = tmp_path / "p.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(sample_rows[0].keys()))
            w.writeheader(); w.writerows(sample_rows)
        t = read_file(p)
        m = suggest_mapping(t)
        rows = project_rows(t, m)
        assert rows[0]["text"] == "这版本地图真不错"
        assert "published_at" in rows[0]


class TestValidator:
    def test_valid_rows(self, sample_rows):
        from liveops.ingest import RawTable
        t = RawTable(columns=list(sample_rows[0].keys()), rows=sample_rows)
        rows = project_rows(t, suggest_mapping(t))
        rep = validate_posts(rows)
        assert rep.valid_count == 2
        assert rep.ok
        assert rep.posts[0].post_id == "100"
        assert rep.posts[0].likes == 12

    def test_missing_required_row_level(self, sample_rows):
        bad = dict(sample_rows[0]); bad.pop("source_url")
        rep = validate_posts([bad, sample_rows[1]])
        assert rep.valid_count == 1
        assert rep.errors[0]["row"] == 1
        assert "source_url" in rep.errors[0]["message"]

    def test_bad_datetime(self, sample_rows):
        bad = dict(sample_rows[0]); bad["published_at"] = "不是时间"
        rep = validate_posts([bad])
        assert rep.valid_count == 0
        assert rep.errors[0]["field"] == "published_at"

    def test_epoch_timestamp(self, sample_rows):
        row = dict(sample_rows[0]); row["published_at"] = 1751431200  # 2026-07-02 附近
        rep = validate_posts([row])
        assert rep.valid_count == 1

    def test_overlength_flagged_not_truncated(self, sample_rows):
        row = dict(sample_rows[0]); row["text"] = "长" * 5000
        rep = validate_posts([row])
        assert rep.valid_count == 1
        assert "overlength" in rep.posts[0].flags
        assert len(rep.posts[0].text) == 5000  # 不截断

    def test_all_invalid(self, sample_rows):
        rep = validate_posts([{**sample_rows[0], "text": ""}])
        assert not rep.ok

    def test_anon_salt_fn(self, sample_rows):
        from liveops.ingest import RawTable
        rows = [{**sample_rows[0], "user_key": "uid-9527"}]
        t = RawTable(columns=list(rows[0].keys()), rows=rows)
        rep = validate_posts(project_rows(t, suggest_mapping(t)), anon_salt_fn=lambda k: "S" + k)
        assert rep.posts[0].anon_user_id == "Suid-9527"
