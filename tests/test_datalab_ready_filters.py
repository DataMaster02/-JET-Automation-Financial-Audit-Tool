import os
import sys
import tempfile
import unittest
import json

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from app import STORE, app, _run_export_task, _run_filter_task
from engine.datastore import FileEntry
from engine.datalab_modules import apply_column_tools


class DataLabReadyFilterTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "A": ["", "x", "x", "y"],
            "B": ["", "", "x", "y"],
            "TUTAR": [-10.0, 0.0, 50.0, -5.0],
            "TARIH": pd.to_datetime(["2026-01-01 07:00", "2026-01-03 12:00", "2026-01-05 19:00", "2026-02-01 10:00"]),
            "KEBIR": ["600.01", "601.01", "102.01", "770.01"],
        })

    def test_core_ready_filters(self):
        empty_any = apply_column_tools(self.df, {"op": "ready_filter", "filter_id": "empty", "columns": ["A", "B"], "column_method": "any", "params": {}})
        empty_all = apply_column_tools(self.df, {"op": "ready_filter", "filter_id": "empty", "columns": ["A", "B"], "column_method": "all", "params": {}})
        neg = apply_column_tools(self.df, {"op": "ready_filter", "filter_id": "negative", "columns": ["TUTAR"], "column_method": "any", "params": {}})
        dup = apply_column_tools(self.df, {"op": "ready_filter", "filter_id": "duplicates", "columns": ["A"], "column_method": "combination", "params": {}})
        dates = apply_column_tools(self.df, {"op": "ready_filter", "filter_id": "date_between", "columns": ["TARIH"], "column_method": "any", "params": {"start_date": "2026-01-01", "end_date": "2026-01-31"}})
        hours = apply_column_tools(self.df, {"op": "ready_filter", "filter_id": "after_hours", "columns": ["TARIH"], "column_method": "any", "params": {"work_start": "08:00", "work_end": "18:00", "weekend_as_after_hours": False}})
        self.assertEqual(len(empty_any), 2)
        self.assertEqual(len(empty_all), 1)
        self.assertEqual(len(neg), 2)
        self.assertEqual(len(dup), 2)
        self.assertEqual(len(dates), 3)
        self.assertEqual(len(hours), 2)

    def test_ready_filter_chain_and_account_codes(self):
        df = pd.DataFrame({
            "KEBIR": ["600.01", "601.01", "102.01", "770.01"],
            "TUTAR": [100, -50, 0, 250],
        })
        config = {
            "op": "ready_filter_chain",
            "chain_logic": "and",
            "chain": [
                {
                    "op": "ready_filter",
                    "filter_id": "account_codes",
                    "filter_name": "Hesap",
                    "columns": ["KEBIR"],
                    "column_method": "any",
                    "params": {"include_accounts": "600\n601", "prefix_len": 3},
                },
                {
                    "op": "ready_filter",
                    "filter_id": "negative",
                    "filter_name": "Negatif",
                    "columns": ["TUTAR"],
                    "column_method": "any",
                    "params": {},
                },
            ],
        }
        out = apply_column_tools(df, config)
        self.assertEqual(out["KEBIR"].tolist(), ["601.01"])

    def test_financial_duplicate_invoice_filter(self):
        df = pd.DataFrame({
            "FATURA": ["A-1", "A-1", "B-2"],
            "TEDARIKCI": ["X", "X", "Y"],
            "TUTAR": [1000.0, 1000.0, 900.0],
        })
        out = apply_column_tools(df, {
            "op": "ready_filter",
            "filter_id": "duplicate_invoice_payment",
            "filter_name": "Mukerrer",
            "columns": ["FATURA", "TEDARIKCI", "TUTAR"],
            "column_method": "combination",
            "params": {"amount_col": "TUTAR", "min_count": 2},
        })
        self.assertEqual(len(out), 2)
        self.assertIn("Duplicate Sayısı", out.columns)

    def test_xlsx_export_writes_real_xlsx_without_double_extension(self):
        entry = FileEntry("kaynak.xlsx", "virtual://kaynak.xlsx")
        entry.df = pd.DataFrame({"A": [1, None], "B": ["x", ""]})
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_export_task("kaynak.xlsx", "xlsx", "utf-8-sig", tmp)
            self.assertTrue(result["ok"])
            out_path = os.path.join(tmp, "kaynak.xlsx")
            self.assertTrue(os.path.exists(out_path), result)
            self.assertFalse(os.path.exists(os.path.join(tmp, "kaynak.xlsx.xlsx")))
            loaded = pd.read_excel(out_path)
            self.assertEqual(list(loaded.columns), ["A", "B"])

    def test_xlsx_export_writes_empty_dataset_headers(self):
        entry = FileEntry("empty.xlsx", "virtual://empty.xlsx")
        entry.df = pd.DataFrame(columns=["A", "B"])
        entry.rows = 0
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_export_task("empty.xlsx", "xlsx", "utf-8-sig", tmp)
            self.assertTrue(result["ok"])
            loaded = pd.read_excel(os.path.join(tmp, "empty.xlsx"))
            self.assertEqual(list(loaded.columns), ["A", "B"])
            self.assertEqual(len(loaded), 0)

    def test_export_task_uses_custom_output_path_and_extra_formats(self):
        entry = FileEntry("custom_export.xlsx", "virtual://custom_export.xlsx")
        entry.df = pd.DataFrame({"A": [1, 2], "Açıklama": ["Türkçe", None]})
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)

        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "denetim_sonuc.json")
            result = _run_export_task("custom_export.xlsx", "csv", "utf-8-sig", tmp, output_path=json_path)
            self.assertTrue(result["ok"])
            self.assertTrue(os.path.exists(json_path), result)
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data[0]["Açıklama"], "Türkçe")

            txt_base = os.path.join(tmp, "denetim_txt")
            result = _run_export_task("custom_export.xlsx", "txt", "utf-8-sig", tmp, output_path=txt_base)
            self.assertTrue(result["ok"])
            txt_path = os.path.join(tmp, "denetim_txt.txt")
            self.assertTrue(os.path.exists(txt_path), result)
            with open(txt_path, "r", encoding="utf-8-sig") as f:
                self.assertIn("Açıklama", f.read())

    def test_binary_export_endpoints_return_real_files(self):
        entry = FileEntry("binary.xlsx", "virtual://binary.xlsx")
        entry.df = pd.DataFrame({
            "Tarih": pd.to_datetime(["2026-01-01"]),
            "Tutar": [123.45],
            "Açıklama": ["Türkçe değer"],
        })
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        client = app.test_client()

        xlsx = client.post("/api/export/download", json={"fileName": "binary.xlsx", "format": "xlsx", "outputName": "sonuc.xlsx"})
        self.assertEqual(xlsx.status_code, 200)
        self.assertEqual(xlsx.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(xlsx.data)
            tmp_path = tmp.name
        try:
            loaded = pd.read_excel(tmp_path)
            self.assertEqual(loaded.loc[0, "Açıklama"], "Türkçe değer")
            self.assertAlmostEqual(float(loaded.loc[0, "Tutar"]), 123.45)
        finally:
            os.unlink(tmp_path)

        csv = client.post("/api/export/download", json={"fileName": "binary.xlsx", "format": "csv", "outputName": "sonuc"})
        self.assertEqual(csv.status_code, 200)
        self.assertIn("text/csv", csv.content_type)
        self.assertIn("Türkçe değer", csv.data.decode("utf-8-sig"))

        json_resp = client.post("/api/export/download", json={"fileName": "binary.xlsx", "format": "json", "outputName": "sonuc"})
        self.assertEqual(json_resp.status_code, 200)
        self.assertIn("application/json", json_resp.content_type)
        self.assertEqual(json.loads(json_resp.data.decode("utf-8"))[0]["Açıklama"], "Türkçe değer")

        txt = client.post("/api/export/download", json={"fileName": "binary.xlsx", "format": "txt", "outputName": "sonuc"})
        self.assertEqual(txt.status_code, 200)
        self.assertIn("text/plain", txt.content_type)
        self.assertIn("Türkçe değer", txt.data.decode("utf-8-sig"))

    def test_filtered_xlsx_export_endpoint(self):
        entry = FileEntry("filtered.xlsx", "virtual://filtered.xlsx")
        entry.df = self.df.copy()
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        client = app.test_client()
        resp = client.post("/api/datalab/filter/export", json={
            "fileName": "filtered.xlsx",
            "format": "xlsx",
            "outputName": "filtered_result",
            "config": {"op": "ready_filter", "filter_id": "negative", "columns": ["TUTAR"], "column_method": "any", "params": {}},
        })
        self.assertEqual(resp.status_code, 200)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(resp.data)
            tmp_path = tmp.name
        try:
            loaded = pd.read_excel(tmp_path)
            self.assertEqual(len(loaded), 2)
            self.assertTrue((loaded["TUTAR"] < 0).all())
        finally:
            os.unlink(tmp_path)

    def test_preview_count_and_new_dataset_save(self):
        entry = FileEntry("save_source.xlsx", "virtual://save_source.xlsx")
        entry.df = self.df.copy()
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        cfg = {
            "op": "ready_filter",
            "filter_id": "account_codes",
            "columns": ["KEBIR"],
            "column_method": "any",
            "params": {"include_accounts": "600\n601", "prefix_len": 3},
            "action": "new",
            "save_as": "save_source.xlsx_Filtre",
        }
        client = app.test_client()
        preview = client.post("/api/datalab/filter/preview", json={"fileName": "save_source.xlsx", "config": cfg, "limit": 20})
        self.assertEqual(preview.status_code, 200)
        data = preview.get_json()
        self.assertEqual(data["totalRows"], 4)
        self.assertEqual(data["resultRows"], 2)
        self.assertLessEqual(len(data["rows"]), 20)

        result = _run_filter_task("save_source.xlsx", cfg)
        self.assertTrue(result["ok"])
        self.assertEqual(result["fileName"], "save_source_Filtre")
        saved = STORE.get_df("save_source_Filtre")
        self.assertIsNotNone(saved)
        self.assertEqual(len(saved), 2)

    def test_unmatched_scope_save(self):
        entry = FileEntry("unmatched.xlsx", "virtual://unmatched.xlsx")
        entry.df = self.df.copy()
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        result = _run_filter_task("unmatched.xlsx", {
            "op": "ready_filter",
            "filter_id": "negative",
            "columns": ["TUTAR"],
            "column_method": "any",
            "params": {},
            "action": "new",
            "save_scope": "unmatched",
            "save_as": "unmatched_result",
        })
        self.assertTrue(result["ok"])
        saved = STORE.get_df("unmatched_result")
        self.assertEqual(len(saved), 2)
        self.assertTrue((saved["TUTAR"] >= 0).all())


if __name__ == "__main__":
    unittest.main()
