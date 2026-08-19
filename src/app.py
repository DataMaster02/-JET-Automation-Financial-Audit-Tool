# ================================================================
# JET OTOMASYON ARACI v4.3 — ANA UYGULAMA
# Flask | JetExecutionEngine | Streaming Reader | DataStore
# Tamamen offline | CPU paralel | GB seviyesi dosya desteği
# ================================================================

import sys, os, threading, webbrowser, time, traceback, logging, gc, tempfile, uuid, re, io

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger("jet.app")

def resource_path(rel: str) -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.reader    import stream_file, get_sheet_names, get_format
from engine.datastore import DataStore, FileEntry, safe_fill_dataframe
from engine.executor  import JetExecutionEngine, TaskStatus
from engine.analyses  import run_kullanici, run_kelime, run_unusual

# Yeni Modüller
from engine.datalab import initialize_datalab_formulas
from engine.datalab.registry import get_all_formulas
from engine.datalab.formula_engine import execute_workflow
from engine.datalab_modules import run_module_preview, run_module_execute, build_profile, apply_column_tools, join_dataframes
from engine.notebook_kernel import run_notebook_cell, create_safe_env

import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, send_file

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024

FAST_XLSX_SHEET_SCAN_LIMIT = 20 * 1024 * 1024

STORE  = DataStore()
ENGINE = JetExecutionEngine.get()
PENDING_UPLOADS = {}

# Notebook durum yönetimi
NOTEBOOK_ENVS = {} # {dataset_name: env_dict}

def _out(name="JET_Ciktilari"):
    p = os.path.join(os.path.expanduser("~"), "Desktop", name)
    os.makedirs(p, exist_ok=True)
    return p

def _dataset_df(name):
    df = STORE.get_df(name)
    if df is None:
        raise ValueError(f'Veri yuklenmedi veya {name} bulunamadi')
    return df

@app.route('/')
def index():
    with open(resource_path('index.html'), 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ── Dosya yükle ──────────────────────────────────────────────
@app.route('/api/upload', methods=['POST'])
def api_upload():
    try:
        file   = request.files.get('file')
        sheet  = request.form.get('sheet') or None
        sep    = request.form.get('sep') or None
        enc    = request.form.get('encoding') or None
        skipr  = int(request.form.get('skiprows', 0))
        headerr= int(request.form.get('headerRow', 0))
        if not file:
            return jsonify({'error': 'Dosya yok'}), 400

        fname = file.filename
        ext   = get_format(fname)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext,
                                          prefix=f'jet_{fname[:20]}_')
        file.save(tmp.name)
        tmp.close()

        file_size = os.path.getsize(tmp.name)
        sheet_names = []
        if ext in ['.xlsx', '.xlsm', '.xls']:
            sheet_names = get_sheet_names(tmp.name)
            if sheet_names and not sheet:
                upload_id = uuid.uuid4().hex
                PENDING_UPLOADS[upload_id] = {
                    'filepath': tmp.name,
                    'fname': fname,
                    'sheet_names': sheet_names,
                    'sep': sep,
                    'enc': enc,
                    'skipr': skipr,
                    'headerr': headerr,
                    'created_at': time.time(),
                    'file_size': file_size,
                }
                return jsonify({
                    'ok': True,
                    'needsSheetSelection': True,
                    'uploadId': upload_id,
                    'fileName': fname,
                    'sheetNames': sheet_names,
                    'defaultSheet': sheet_names[0],
                    'fileSizeMb': round(file_size / 1024 / 1024, 2),
                })

        task_id = ENGINE.submit(
            jet_id      = f"LOAD_{fname[:30]}",
            fn          = _load_file_task,
            filepath    = tmp.name,
            fname       = fname,
            sheet       = sheet or (sheet_names[0] if sheet_names else None),
            sheet_names = sheet_names,
            sep=sep, enc=enc, skipr=skipr, headerr=headerr,
            keep_source=bool(sheet_names),
            priority=1,
        )
        return jsonify({'ok': True, 'task_id': task_id,
                        'fileName': fname, 'sheetNames': sheet_names})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/upload-sheet', methods=['POST'])
def api_upload_sheet():
    try:
        data = request.json or {}
        upload_id = data.get('uploadId')
        pending = PENDING_UPLOADS.get(upload_id)
        if not pending:
            return jsonify({'error': 'Sheet secimi zaman asimina ugradi veya dosya bulunamadi'}), 404

        selected = data.get('sheets') or data.get('sheet') or []
        if isinstance(selected, str):
            selected = [selected]
        selected = [s for s in selected if s in pending['sheet_names']]
        if not selected:
            return jsonify({'error': 'Yuklenecek sheet secilmedi'}), 400

        skipr = int(data.get('skiprows', pending.get('skipr', 0)) or 0)
        headerr = int(data.get('headerRow', pending.get('headerr', 0)) or 0)
        task_ids = []
        for sheet in selected:
            dataset_name = pending['fname'] if len(selected) == 1 else f"{os.path.splitext(pending['fname'])[0]} - {sheet}{os.path.splitext(pending['fname'])[1]}"
            task_id = ENGINE.submit(
                jet_id=f"LOAD_{dataset_name[:30]}",
                fn=_load_file_task,
                filepath=pending['filepath'],
                fname=pending['fname'],
                sheet=sheet,
                sheet_names=pending['sheet_names'],
                sep=pending.get('sep'),
                enc=pending.get('enc'),
                skipr=skipr,
                headerr=headerr,
                keep_source=True,
                dataset_name=dataset_name,
                priority=1,
            )
            task_ids.append(task_id)
        PENDING_UPLOADS.pop(upload_id, None)
        return jsonify({'ok': True, 'task_ids': task_ids, 'task_id': task_ids[0] if task_ids else None})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/upload-sheet-preview', methods=['POST'])
def api_upload_sheet_preview():
    try:
        data = request.json or {}
        pending = PENDING_UPLOADS.get(data.get('uploadId'))
        if not pending:
            return jsonify({'error': 'Dosya bulunamadi'}), 404
        sheet = data.get('sheet') or pending['sheet_names'][0]
        if sheet not in pending['sheet_names']:
            return jsonify({'error': 'Sheet bulunamadi'}), 404
        rows = []
        cols = []
        for i, chunk in enumerate(stream_file(
            pending['filepath'],
            sheet=sheet,
            sep=pending.get('sep'),
            encoding=pending.get('enc'),
            skiprows=int(data.get('skiprows', pending.get('skipr', 0)) or 0),
            header_row=int(data.get('headerRow', pending.get('headerr', 0)) or 0),
            chunk=10,
        )):
            cols = list(chunk.columns)
            rows = chunk.head(10).to_dict(orient='records')
            break
        return jsonify({'ok': True, 'columns': cols, 'rows': rows})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/cancel-upload', methods=['POST'])
def api_cancel_upload():
    try:
        upload_id = (request.json or {}).get('uploadId')
        pending = PENDING_UPLOADS.pop(upload_id, None)
        if pending:
            try:
                os.unlink(pending['filepath'])
            except Exception:
                pass
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _load_file_task(filepath, fname, sheet, sheet_names,
                    sep, enc, skipr, headerr, keep_source=False,
                    dataset_name=None, _progress_cb=None):
    try:
        if _progress_cb: _progress_cb(10, "Dosya okunuyor...")
        
        ext = get_format(fname)
        frames = []
        if ext in ['csv', 'txt', 'tsv']:
            loaded_rows = 0
            for chunk in pd.read_csv(filepath, sep=sep, encoding=enc, skiprows=skipr, header=headerr, chunksize=100000, low_memory=False, dtype=str):
                frames.append(chunk)
                loaded_rows += len(chunk)
                if _progress_cb: _progress_cb(50, f"Okunuyor: {loaded_rows} satır...")
        else:
            for chunk in stream_file(filepath, sheet=sheet, sep=sep, encoding=enc,
                                  skiprows=skipr, header_row=headerr,
                                  progress_cb=_progress_cb):
                frames.append(chunk)

        if not frames:
            return {'error': 'Dosya boş'}

        if _progress_cb: _progress_cb(80, "Veri işleniyor...")
        df = safe_fill_dataframe(pd.concat(frames, ignore_index=True))
        del frames; gc.collect()

        if _progress_cb: _progress_cb(90, "İndeks oluşturuluyor...")

        # Avoid name collision
        base_name = dataset_name or fname
        base_seed = base_name
        idx = 1
        while STORE.get_entry(base_name):
            base_name = f"{base_seed}_{idx}"
            idx += 1

        entry = FileEntry(name=base_name, filepath=filepath)
        entry.df             = df
        entry.rows           = len(df)
        entry.col_names      = list(df.columns)
        entry.sheet_names    = sheet_names
        entry.selected_sheet = sheet or (sheet_names[0] if sheet_names else '')
        entry.load_options   = {'sep': sep, 'enc': enc, 'skipr': skipr, 'headerr': headerr}
        entry.infer_types()
        if len(df) <= 250_000:
            entry.build_index(max_unique=5_000)

        STORE.add_entry(entry)
        STORE.cache_entry(base_name)

        if _progress_cb: _progress_cb(100, "Tamamlandı")
        return {'ok': True, 'fileName': base_name, 'fileInfos': STORE.info_list()}
    except Exception as e:
        logger.error(f"Yükleme hatası ({fname}): {e}")
        raise
    finally:
        if not keep_source:
            try: os.unlink(filepath)
            except: pass


@app.route('/api/upload-status', methods=['POST'])
def api_upload_status():
    try:
        task_id = request.json.get('task_id')
        s = ENGINE.status(task_id)
        if not s: return jsonify({'error': 'Task yok'}), 404
        if s['status'] == TaskStatus.DONE.value:
            s['fileInfos'] = STORE.info_list()
        return jsonify(s)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/select-sheet', methods=['POST'])
def api_select_sheet():
    try:
        data  = request.json
        fname = data['fileName']
        sheet = data['sheet']
        entry = STORE.get_entry(fname)
        if not entry: return jsonify({'error': 'Dosya yok'}), 404
        task_id = ENGINE.submit(f"SHEET_{fname[:20]}", _reload_sheet_task,
                                fname=fname, sheet=sheet, priority=1)
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sheet-names', methods=['POST'])
def api_sheet_names():
    try:
        data = request.json or {}
        fname = data.get('fileName')
        entry = STORE.get_entry(fname)
        if not entry:
            return jsonify({'error': 'Dosya yok'}), 404
        names = entry.sheet_names or get_sheet_names(entry.filepath)
        if names and names != entry.sheet_names:
            entry.sheet_names = names
        return jsonify({'ok': True, 'sheetNames': names})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _reload_sheet_task(fname, sheet, _progress_cb=None):
    entry = STORE.get_entry(fname)
    if not entry: raise ValueError(f"{fname} bulunamadı")
    opts = entry.load_options or {}
    frames = list(stream_file(entry.filepath, sheet=sheet,
                               sep=opts.get('sep'), encoding=opts.get('enc'),
                               skiprows=opts.get('skipr', 0),
                               header_row=opts.get('headerr', 0),
                               progress_cb=_progress_cb))
    df = safe_fill_dataframe(pd.concat(frames, ignore_index=True))
    entry.df = df; entry.rows = len(df)
    entry.col_names = list(df.columns); entry.selected_sheet = sheet
    entry.infer_types(); entry.build_index()
    return {'ok': True, 'fileInfos': STORE.info_list()}


@app.route('/api/remove-file', methods=['POST'])
def api_remove_file():
    try:
        fname = request.json.get('fileName')
        entry = STORE.get_entry(fname)
        filepath = entry.filepath if entry else ''
        STORE.remove_entry(fname)
        if filepath and not filepath.startswith('virtual://'):
            still_used = any(e.filepath == filepath for e in STORE.all_entries())
            if not still_used and os.path.basename(filepath).startswith('jet_'):
                try:
                    os.unlink(filepath)
                except Exception:
                    pass
        if fname in NOTEBOOK_ENVS:
            del NOTEBOOK_ENVS[fname]
        return jsonify({'ok': True, 'fileInfos': STORE.info_list()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clear-files', methods=['POST'])
def api_clear_files():
    paths = [e.filepath for e in STORE.all_entries()
             if e.filepath and not e.filepath.startswith('virtual://')]
    STORE.clear()
    NOTEBOOK_ENVS.clear()
    for path in set(paths):
        if os.path.basename(path).startswith('jet_'):
            try:
                os.unlink(path)
            except Exception:
                pass
    for upload_id, pending in list(PENDING_UPLOADS.items()):
        try:
            os.unlink(pending['filepath'])
        except Exception:
            pass
        PENDING_UPLOADS.pop(upload_id, None)
    return jsonify({'ok': True})


@app.route('/api/file-infos', methods=['POST'])
def api_file_infos():
    return jsonify({'ok': True, 'fileInfos': STORE.info_list()})


# ── Önizleme ─────────────────────────────────────────────────
@app.route('/api/preview', methods=['POST'])
def api_preview():
    try:
        d = request.json or {}
        fname = d.get('fileName')
        if not fname: return jsonify({'error': 'Dosya secilmedi'}), 400
        cols, rows, total = STORE.query(
            file_name=fname,
            page=int(d.get('page', 0)),
            per=int(d.get('perPage', 100)),
            filters=d.get('filters') or None,
            sort_col=d.get('sortCol'),
            sort_asc=d.get('sortAsc', True)
        )
        return jsonify({'ok': True, 'columns': cols, 'rows': rows,
                        'total': total, 'page': d.get('page', 0),
                        'perPage': d.get('perPage', 100)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Append & Export ──────────────────────────────────────────
@app.route('/api/append/run', methods=['POST'])
def api_append_run():
    try:
        d = request.json or {}
        file_names = d.get('fileNames', [])
        new_name = d.get('newName', f"Birlesik_{int(time.time())}")
        if not file_names: return jsonify({'error': 'Birleştirilecek dosya seçilmedi'}), 400
        
        task_id = ENGINE.submit(
            jet_id=f"APPEND_{new_name[:20]}",
            fn=_run_append_task,
            file_names=file_names,
            new_name=new_name,
            priority=2
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _run_append_task(file_names, new_name, _progress_cb=None):
    try:
        if _progress_cb: _progress_cb(10, "Veriler hazırlanıyor...")
        frames = []
        total_rows = 0
        all_cols = set()
        
        for name in file_names:
            df = STORE.get_df(name)
            if df is not None:
                frames.append(df)
                total_rows += len(df)
                all_cols.update(df.columns)
        
        if not frames:
             return {'error': 'Seçilen dosyalar boş veya bulunamadı'}

        if _progress_cb: _progress_cb(50, f"Birleştiriliyor ({total_rows} satır)...")
        
        # Align columns
        for i in range(len(frames)):
            df = frames[i]
            missing_cols = all_cols - set(df.columns)
            for c in missing_cols:
                df[c] = ''
        
        combined_df = safe_fill_dataframe(pd.concat(frames, ignore_index=True))
        
        if _progress_cb: _progress_cb(80, "Sisteme kaydediliyor...")
        
        entry = FileEntry(name=new_name, filepath=f"virtual://{new_name}")
        entry.df = combined_df
        entry.rows = len(combined_df)
        entry.col_names = list(combined_df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        STORE.cache_entry(new_name)
        
        if _progress_cb: _progress_cb(100, "Tamamlandı")
        return {'ok': True, 'fileName': new_name, 'fileInfos': STORE.info_list()}
    except Exception as e:
        logger.error(f"Append hatası: {e}")
        raise

@app.route('/api/append/export', methods=['POST'])
def api_append_export():
    try:
        d = request.json or {}
        file_name = d.get('fileName')
        format = d.get('format', 'csv')
        encoding = d.get('encoding', 'utf-8-sig')
        out_folder = _out(d.get('outputFolder', 'JET_Ciktilari'))
        
        if not file_name: return jsonify({'error': 'Dataset seçilmedi'}), 400
        
        task_id = ENGINE.submit(
            jet_id=f"EXPORT_{file_name[:15]}",
            fn=_run_export_task,
            file_name=file_name,
            format=format,
            encoding=encoding,
            out_folder=out_folder,
            output_name=d.get('outputName') or file_name,
            priority=2
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/export/download', methods=['POST'])
def api_export_download():
    try:
        d = request.json or {}
        file_name = d.get('fileName')
        fmt = str(d.get('format', 'xlsx')).lower()
        if not file_name:
            return jsonify({'error': 'Dataset seçilmedi'}), 400
        df = _dataset_df(file_name)
        download_name = d.get('outputName') or file_name
        return _send_dataframe_export(df, download_name, fmt, d.get('encoding', 'utf-8-sig'))
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/filter/export', methods=['POST'])
def api_datalab_filter_export():
    try:
        d = request.json or {}
        file_name = d.get('fileName')
        fmt = str(d.get('format', 'xlsx')).lower()
        config = d.get('config', {})
        if not file_name:
            return jsonify({'error': 'Dataset seçilmedi'}), 400
        df = _dataset_df(file_name)
        result_df = apply_column_tools(df, config)
        if config.get('save_scope') == 'unmatched':
            result_df = df.loc[~df.index.isin(result_df.index)].copy()
        download_name = d.get('outputName') or config.get('save_as') or f"{_safe_export_name(file_name)}_Filtre"
        return _send_dataframe_export(result_df, download_name, fmt, d.get('encoding', 'utf-8-sig'))
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

def _run_export_task(file_name, format, encoding, out_folder, output_name=None, _progress_cb=None):
    df = STORE.get_df(file_name)
    if df is None:
         return {'error': f'{file_name} bulunamadı'}
    
    if not os.path.isabs(str(out_folder or "")):
        out_folder = _out(out_folder or 'JET_Ciktilari')
    os.makedirs(out_folder, exist_ok=True)
    safe_name = _safe_export_name(output_name or file_name)
    base_path = os.path.join(out_folder, safe_name)
    saved_paths = []
    total_rows = len(df)
    
    if format == 'csv':
        out_path = f"{base_path}.csv"
        if _progress_cb: _progress_cb(50, "CSV yazılıyor...")
        df.to_csv(out_path, index=False, encoding=encoding)
        saved_paths.append(out_path)
    
    elif format == 'txt':
        out_path = f"{base_path}.txt"
        if _progress_cb: _progress_cb(50, "TXT yazılıyor...")
        df.to_csv(out_path, index=False, sep='\t', encoding=encoding)
        saved_paths.append(out_path)
        
    elif format == 'parquet':
        out_path = f"{base_path}.parquet"
        if _progress_cb: _progress_cb(50, "Parquet yazılıyor...")
        df.to_parquet(out_path, index=False)
        saved_paths.append(out_path)
        
    elif format == 'xlsx':
        chunk_size = 1000000 # Excel limit ~1.048.576
        num_chunks = max(1, (total_rows // chunk_size) + (1 if total_rows % chunk_size > 0 else 0))
        
        for i in range(num_chunks):
            chunk_df = df.iloc[i*chunk_size : (i+1)*chunk_size]
            part_suffix = f"_part{i+1}" if num_chunks > 1 else ""
            out_path = f"{base_path}{part_suffix}.xlsx"
            if _progress_cb: _progress_cb(int((i/num_chunks)*100), f"Excel part {i+1}/{num_chunks} yazılıyor...")
            _write_xlsx(chunk_df, out_path)
            saved_paths.append(out_path)
    else:
        return {'error': 'Geçersiz format'}
        
    if _progress_cb: _progress_cb(100, "Dışa aktarma tamamlandı")
    return {'ok': True, 'savedTo': ", ".join(saved_paths)}

def _safe_export_name(file_name):
    name = os.path.basename(str(file_name or "dataset"))
    name = re.sub(r"\.(xlsx|xlsm|xls|csv|txt|tsv|parquet)(?=$|_)", "", name, flags=re.IGNORECASE)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" ._")
    return name[:160] or "dataset"

def _write_xlsx(df, out_path):
    export_df = safe_fill_dataframe(df.copy())
    try:
        with pd.ExcelWriter(out_path, engine='xlsxwriter', engine_kwargs={'options': {'constant_memory': True}}) as writer:
            export_df.to_excel(writer, index=False, sheet_name='Data')
    except ModuleNotFoundError:
        with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Data')

def _write_xlsx_buffer(df):
    bio = io.BytesIO()
    export_df = safe_fill_dataframe(df.copy())
    try:
        with pd.ExcelWriter(bio, engine='xlsxwriter', datetime_format='yyyy-mm-dd hh:mm:ss', date_format='yyyy-mm-dd') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Data')
    except ModuleNotFoundError:
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Data')
    bio.seek(0)
    return bio

def _send_dataframe_export(df, file_name, fmt='xlsx', encoding='utf-8-sig'):
    safe_name = _safe_export_name(file_name)
    if fmt == 'xlsx':
        bio = _write_xlsx_buffer(df)
        return send_file(
            bio,
            as_attachment=True,
            download_name=f"{safe_name}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    if fmt == 'csv':
        data = safe_fill_dataframe(df.copy()).to_csv(index=False, encoding=encoding)
        bio = io.BytesIO(data.encode(encoding or 'utf-8-sig'))
        return send_file(
            bio,
            as_attachment=True,
            download_name=f"{safe_name}.csv",
            mimetype='text/csv; charset=utf-8',
        )
    return jsonify({'error': 'Geçersiz format'}), 400


# ── Analizler ────────────────────────────────────────────────
@app.route('/api/kullanici', methods=['POST'])
def api_kullanici():
    try:
        d = request.json
        df = _dataset_df(d.get('fileName'))
        task_id = ENGINE.submit(
            d.get('jetId', f"JET-KUL-{d.get('fileName')[:10]}"), 
            run_kullanici,
            df=df, user_col=d['userCol'],
            borc_col=d.get('borcCol') or None,
            alacak_col=d.get('alacakCol') or None,
            tutar_kols=d.get('tutarKols') or [],
            output_folder=d.get('outputFolder', 'JET_Ciktilari'),
            template_path=d.get('templatePath', ''),
            priority=int(d.get('priority', 5)),
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/kelime', methods=['POST'])
def api_kelime():
    try:
        d = request.json
        df = _dataset_df(d.get('fileName'))
        task_id = ENGINE.submit(
            d.get('jetId', f"JET-KEL-{d.get('fileName')[:10]}"), 
            run_kelime,
            df=df, scan_cols=d['scanCols'],
            keywords=d['keywords'], scan_mode=d.get('scanMode', 'tam'),
            output_folder=d.get('outputFolder', 'JET_Ciktilari'),
            template_path=d.get('templatePath', ''),
            priority=int(d.get('priority', 5)),
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/unusual', methods=['POST'])
def api_unusual():
    try:
        d = request.json
        df = _dataset_df(d.get('fileName'))
        task_id = ENGINE.submit(
            d.get('jetId', f"JET-UNS-{d.get('fileName')[:10]}"), 
            run_unusual,
            df=df, hesap_col=d['hesapCol'],
            grup_col=d['grupCol'], criteria=d['criteria'],
            match_len=int(d.get('matchLen', 3)),
            output_folder=d.get('outputFolder', 'JET_Ciktilari'),
            template_path=d.get('templatePath', ''),
            priority=int(d.get('priority', 5)),
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

# ── DataLab: Modüller & Notebook ────────────────────────────────────

@app.route('/api/datalab/formulas', methods=['GET', 'POST'])
def api_datalab_formulas():
    return jsonify(get_all_formulas())

@app.route('/api/datalab/module/preview', methods=['POST'])
def api_datalab_module_preview():
    try:
        d = request.json or {}
        df = _dataset_df(d.get('fileName'))
        return jsonify(run_module_preview(df, d.get('config', {})))
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/module/execute', methods=['POST'])
def api_datalab_module_execute():
    try:
        d = request.json or {}
        file_name = d.get('fileName')
        config = d.get('config', {})
        if not file_name:
            return jsonify({'error': 'Dosya seçilmedi'}), 400
        df = _dataset_df(file_name)
        result = run_module_execute(df, config)
        if result.get('error'):
            return jsonify(result), 400
        new_name = config.get('new_dataset_name') or f"{file_name}_{config.get('operation','module')}"
        if config.get('save_as_new', True):
            entry = FileEntry(name=new_name, filepath=f"virtual://{new_name}")
            entry.df = result['df'].copy()
            entry.rows = len(entry.df)
            entry.col_names = list(entry.df.columns)
            entry.infer_types()
            STORE.add_entry(entry)
            STORE.cache_entry(new_name)
            return jsonify({'ok': True, 'fileName': new_name, 'fileInfos': STORE.info_list()})
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/profile', methods=['POST'])
def api_datalab_profile():
    try:
        d = request.json or {}
        df = _dataset_df(d.get('fileName'))
        return jsonify({'ok': True, 'profile': build_profile(df)})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/tools/apply', methods=['POST'])
def api_datalab_tools_apply():
    try:
        d = request.json or {}
        file_name = d.get('fileName')
        config = d.get('config', {})
        if not file_name:
            return jsonify({'error': 'Dataset seçilmedi'}), 400
        df = _dataset_df(file_name)
        if config.get('op') == 'join':
            right_name = config.get('right_file')
            if not right_name:
                return jsonify({'error': 'Join icin ikinci dataset secilmedi'}), 400
            right_df = _dataset_df(right_name)
            result_df = join_dataframes(df, right_df, config)
            config['replace'] = False
            config['save_as'] = config.get('save_as') or f"{file_name}_join_{right_name}"
        else:
            result_df = apply_column_tools(df, config)
        new_name = config.get('save_as') or file_name
        if config.get('replace', True):
            STORE.update_entry_df(file_name, result_df)
            return jsonify({'ok': True, 'fileName': file_name, 'fileInfos': STORE.info_list()})
        entry = FileEntry(name=new_name, filepath=f"virtual://{new_name}")
        entry.df = safe_fill_dataframe(result_df.copy())
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        STORE.cache_entry(new_name)
        return jsonify({'ok': True, 'fileName': new_name, 'fileInfos': STORE.info_list()})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/filter/preview', methods=['POST'])
def api_datalab_filter_preview():
    try:
        d = request.json or {}
        file_name = d.get('fileName')
        config = d.get('config', {})
        if not file_name:
            return jsonify({'error': 'Dataset secilmedi'}), 400
        df = _dataset_df(file_name)
        result_df = apply_column_tools(df, config)
        sample = safe_fill_dataframe(result_df.head(int(d.get('limit', 50))).copy())
        return jsonify({
            'ok': True,
            'totalRows': len(df),
            'resultRows': len(result_df),
            'excludedRows': max(0, len(df) - len(result_df)),
            'columns': list(sample.columns),
            'rows': sample.to_dict('records'),
        })
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/filter/run', methods=['POST'])
def api_datalab_filter_run():
    try:
        d = request.json or {}
        file_name = d.get('fileName')
        config = d.get('config', {})
        if not file_name:
            return jsonify({'error': 'Dataset secilmedi'}), 400
        task_id = ENGINE.submit(
            jet_id=f"FILTER_{file_name[:20]}",
            fn=_run_filter_task,
            file_name=file_name,
            config=config,
            priority=2,
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

def _save_virtual_dataset(name, df):
    entry = FileEntry(name=name, filepath=f"virtual://{name}")
    entry.df = safe_fill_dataframe(df.copy())
    entry.rows = len(entry.df)
    entry.col_names = list(entry.df.columns)
    entry.infer_types()
    STORE.add_entry(entry)
    STORE.cache_entry(name)
    return entry

def _run_filter_task(file_name, config, _progress_cb=None):
    if _progress_cb:
        _progress_cb(10, "Filtre hazirlaniyor...")
    df = _dataset_df(file_name)
    if _progress_cb:
        _progress_cb(35, f"Filtre uygulanıyor ({len(df):,} satir)...")
    result_df = apply_column_tools(df, config)
    matched_rows = len(result_df)
    if config.get('save_scope') == 'unmatched':
        result_df = df.loc[~df.index.isin(result_df.index)].copy()
    action = config.get('action') or ('replace' if config.get('replace') else 'new')
    new_name = _safe_export_name(config.get('save_as') or f"{_safe_export_name(file_name)}_Filtre")

    if _progress_cb:
        _progress_cb(75, "Sonuc kaydediliyor...", len(result_df), len(df))

    if action == 'replace':
        STORE.update_entry_df(file_name, result_df)
        out_name = file_name
    elif action == 'append':
        target_name = config.get('append_to') or new_name
        target_df = STORE.get_df(target_name)
        if target_df is None:
            _save_virtual_dataset(target_name, result_df)
        else:
            combined = safe_fill_dataframe(pd.concat([target_df, result_df], ignore_index=True, sort=False))
            STORE.update_entry_df(target_name, combined)
        out_name = target_name
    else:
        _save_virtual_dataset(new_name, result_df)
        out_name = new_name

    if _progress_cb:
        _progress_cb(100, "Tamamlandi", len(result_df), len(df))
    return {'ok': True, 'fileName': out_name, 'rows': len(result_df), 'matchedRows': matched_rows, 'fileInfos': STORE.info_list()}

@app.route('/api/datalab/execute_workflow', methods=['POST'])
def api_datalab_execute_workflow():
    try:
        d = request.json or {}
        fname = d.get('fileName')
        workflow = d.get('workflow', [])
        new_name = d.get('newName', f"{fname}_Datalab")

        if not fname or not workflow:
            return jsonify({'error': 'Dataset ve workflow gerekli'}), 400

        task_id = ENGINE.submit(
            jet_id=f"DATALAB_{new_name[:20]}",
            fn=_run_datalab_workflow,
            file_name=fname,
            workflow=workflow,
            new_name=new_name,
            priority=2
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

def _run_datalab_workflow(file_name, workflow, new_name, _progress_cb=None):
    try:
        if _progress_cb: _progress_cb(10, "Veri yükleniyor...")
        df = STORE.get_df(file_name)
        if df is None:
            return {'error': 'Dataset bulunamadı'}

        if _progress_cb: _progress_cb(30, "Workflow çalıştırılıyor...")
        result_df = execute_workflow(df, workflow)
        
        if _progress_cb: _progress_cb(80, "Sonuç kaydediliyor...")
        entry = FileEntry(name=new_name, filepath=f"virtual://{new_name}")
        entry.df = safe_fill_dataframe(result_df.copy())
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        STORE.cache_entry(new_name)

        if _progress_cb: _progress_cb(100, "Tamamlandı")
        return {'ok': True, 'fileName': new_name, 'fileInfos': STORE.info_list()}
    except Exception as e:
        logger.error(f"DataLab workflow hatası: {e}")
        raise

@app.route('/api/datalab/notebook/run', methods=['POST'])
def api_datalab_notebook_run():
    try:
        d = request.json or {}
        fname = d.get('fileName')
        code = d.get('code', '')
        
        if not fname: return jsonify({'error': 'Dataset seçilmedi'}), 400
        
        df = STORE.get_df(fname)
        if df is None: return jsonify({'error': 'Dataset bulunamadı'}), 404

        # Initialize environment if not exists
        if fname not in NOTEBOOK_ENVS:
            NOTEBOOK_ENVS[fname] = create_safe_env(df)
            
        env = NOTEBOOK_ENVS[fname]
        res = run_notebook_cell(code, env)
        return jsonify(res)
        
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/notebook/save', methods=['POST'])
def api_datalab_notebook_save():
    try:
        d = request.json or {}
        fname = d.get('fileName')
        new_name = d.get('newName', f"{fname}_NotebookOut")
        variable = d.get('variable', 'df')
        
        if not fname or fname not in NOTEBOOK_ENVS: 
            return jsonify({'error': 'Notebook ortamı bulunamadı'}), 400
            
        env = NOTEBOOK_ENVS[fname]
        obj = env.get('_last_result') if variable == '_last_result' else env.get(variable)
        
        if isinstance(obj, pd.Series):
            df = obj.to_frame(name=obj.name or 'value')
        elif isinstance(obj, pd.DataFrame):
            df = obj
        else:
            return jsonify({'error': 'Notebook içindeki df değişkeni geçersiz'}), 400

        entry = FileEntry(name=new_name, filepath=f"virtual://{new_name}")
        entry.df = safe_fill_dataframe(df.copy())
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        STORE.cache_entry(new_name)
        
        return jsonify({'ok': True, 'fileName': new_name, 'fileInfos': STORE.info_list()})
    except Exception as e:
         return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/notebook/export', methods=['POST'])
def api_datalab_notebook_export():
    try:
        d = request.json or {}
        fname = d.get('fileName')
        variable = d.get('variable', '_last_result')
        new_name = d.get('newName') or f"{fname}_{variable}_Export"
        if not fname or fname not in NOTEBOOK_ENVS:
            return jsonify({'error': 'Notebook ortami bulunamadi'}), 400
        env = NOTEBOOK_ENVS[fname]
        obj = env.get('_last_result') if variable == '_last_result' else env.get(variable)
        if isinstance(obj, pd.Series):
            df = obj.to_frame(name=obj.name or 'value')
        elif isinstance(obj, pd.DataFrame):
            df = obj
        else:
            return jsonify({'error': f'{variable} DataFrame/Series degil'}), 400

        entry = FileEntry(name=new_name, filepath=f"virtual://{new_name}")
        entry.df = safe_fill_dataframe(df.copy())
        entry.rows = len(entry.df)
        entry.col_names = list(entry.df.columns)
        entry.infer_types()
        STORE.add_entry(entry)
        STORE.cache_entry(new_name)

        task_id = ENGINE.submit(
            jet_id=f"EXPORT_{new_name[:15]}",
            fn=_run_export_task,
            file_name=new_name,
            format=d.get('format', 'xlsx'),
            encoding=d.get('encoding', 'utf-8-sig'),
            out_folder=d.get('outputFolder', 'JET_Ciktilari'),
            priority=2,
        )
        return jsonify({'ok': True, 'fileName': new_name, 'fileInfos': STORE.info_list(), 'task_id': task_id})
    except Exception as e:
         return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/datalab/notebook/reset', methods=['POST'])
def api_datalab_notebook_reset():
    try:
        d = request.json or {}
        fname = d.get('fileName')
        if not fname: return jsonify({'error': 'Dataset seçilmedi'}), 400
        
        df = STORE.get_df(fname)
        if df is None: return jsonify({'error': 'Dataset bulunamadı'}), 404
        
        NOTEBOOK_ENVS[fname] = create_safe_env(df)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

# ── Görev yönetimi ───────────────────────────────────────────
@app.route('/api/task-status', methods=['POST'])
def api_task_status():
    try:
        s = ENGINE.status(request.json.get('task_id'))
        if not s: return jsonify({'error': 'Task yok'}), 404
        return jsonify(s)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/all-tasks', methods=['POST'])
def api_all_tasks():
    try:
        return jsonify({'ok': True, 'tasks': ENGINE.all_tasks(),
                        'active': ENGINE.active_count(),
                        'queued': ENGINE.queue_size(),
                        'workers': ENGINE._max_workers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cancel-task', methods=['POST'])
def api_cancel_task():
    try:
        ok = ENGINE.cancel(request.json.get('task_id'))
        return jsonify({'ok': ok})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/system-info', methods=['POST'])
def api_system_info():
    try:
        import psutil
        proc = psutil.Process()
        vm   = psutil.virtual_memory()
        return jsonify({
            'ok': True,
            'cpu_count':    os.cpu_count(),
            'cpu_pct':      psutil.cpu_percent(interval=0.1),
            'ram_total_mb': round(vm.total / 1024 / 1024),
            'ram_used_mb':  round(vm.used  / 1024 / 1024),
            'ram_pct':      vm.percent,
            'proc_ram_mb':  round(proc.memory_info().rss / 1024 / 1024),
            'active_tasks': ENGINE.active_count(),
            'queued_tasks': ENGINE.queue_size(),
            'workers':      ENGINE._max_workers,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── DataLab ─────────────────────────────────────────────────
@app.route('/api/datalab/execute', methods=['POST'])
def api_datalab_execute():
    try:
        data = request.json or {}
        file_name = data.get('fileName')
        formula_key = data.get('formulaKey')
        params = data.get('params', {})
        output_var = data.get('outputVar', 'result')
        
        if not file_name:
            return jsonify({'error': 'Dosya seçilmedi'}), 400
        if not formula_key:
            return jsonify({'error': 'İşlem seçilmedi'}), 400
        
        task_id = ENGINE.submit(
            jet_id=f"DATALAB_{formula_key[:20]}",
            fn=_run_datalab_task,
            file_name=file_name,
            formula_key=formula_key,
            params=params,
            output_var=output_var,
            priority=2
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

def _run_datalab_task(file_name, formula_key, params, output_var, _progress_cb=None):
    try:
        from engine.datalab import get_registry
        
        if _progress_cb: _progress_cb(10, "Formül registry'i hazırlanıyor...")
        
        df = _dataset_df(file_name)
        registry = get_registry()
        
        # Parametreleri çöz (sütun adlarını DataFrame'den al)
        resolved_params = {}
        for param_name, param_value in params.items():
            if isinstance(param_value, str) and param_value.startswith('$'):
                # Sütun referansı
                col_name = param_value[1:]
                if col_name in df.columns:
                    resolved_params[param_name] = df[col_name].values
                else:
                    raise ValueError(f"Sütun bulunamadı: {col_name}")
            else:
                resolved_params[param_name] = param_value
        
        if _progress_cb: _progress_cb(50, f"İşlem çalıştırılıyor: {formula_key}...")
        
        # Formülü çalıştır
        result = registry.execute(formula_key, **resolved_params)
        
        if _progress_cb: _progress_cb(90, "Sonuç işleniyor...")
        
        # Sonucu formatla
        result_data = None
        if isinstance(result, np.ndarray):
            result_data = result.tolist()
        elif isinstance(result, pd.DataFrame):
            result_data = result.to_dict('records')
        elif isinstance(result, (list, dict)):
            result_data = result
        else:
            result_data = str(result)
        
        if _progress_cb: _progress_cb(100, "Tamamlandı")
        
        return {
            'ok': True,
            'outputVar': output_var,
            'result': result_data,
            'resultType': type(result).__name__
        }
    except Exception as e:
        logger.error(f"DataLab hatası: {e}")
        raise

@app.route('/api/datalab/workflow', methods=['POST'])
def api_datalab_workflow():
    try:
        data = request.json or {}
        file_name = data.get('fileName')
        steps = data.get('steps', [])
        
        if not file_name:
            return jsonify({'error': 'Dosya seçilmedi'}), 400
        if not steps:
            return jsonify({'error': 'İş akışı adımı yok'}), 400
        
        task_id = ENGINE.submit(
            jet_id=f"WORKFLOW_{file_name[:15]}",
            fn=_run_workflow_task,
            file_name=file_name,
            steps=steps,
            priority=2
        )
        return jsonify({'ok': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

def _run_workflow_task(file_name, steps, _progress_cb=None):
    try:
        from engine.datalab import get_registry, WorkflowBuilder
        
        if _progress_cb: _progress_cb(10, "İş akışı hazırlanıyor...")
        
        df = _dataset_df(file_name)
        registry = get_registry()
        builder = WorkflowBuilder(registry)
        
        # İlk veri
        data = {'__df': df}
        for col in df.columns:
            data[col] = df[col].values
        
        # Adımları ekle
        for i, step in enumerate(steps):
            formula_key = step.get('formulaKey')
            output_var = step.get('outputVar', f'result_{i}')
            params = step.get('params', {})
            
            # Parametreleri çöz
            resolved_params = {}
            for param_name, param_value in params.items():
                if isinstance(param_value, str) and param_value.startswith('$'):
                    var_name = param_value[1:]
                    if var_name in data:
                        resolved_params[param_name] = data[var_name]
                    else:
                        raise ValueError(f"Değişken bulunamadı: {var_name}")
                else:
                    resolved_params[param_name] = param_value
            
            builder.add_step(formula_key, output_var, **resolved_params)
        
        if _progress_cb: _progress_cb(50, f"İş akışı çalıştırılıyor ({len(steps)} adım)...")
        
        # İş akışını çalıştır
        results = builder.execute(data)
        
        if _progress_cb: _progress_cb(90, "Sonuçlar işleniyor...")
        
        # Sonuçları formatla
        formatted_results = {}
        for key, val in results.items():
            if key.startswith('__'):
                continue
            if isinstance(val, np.ndarray):
                formatted_results[key] = val.tolist()
            elif isinstance(val, pd.DataFrame):
                formatted_results[key] = val.to_dict('records')
            elif isinstance(val, (list, dict)):
                formatted_results[key] = val
            else:
                formatted_results[key] = str(val)
        
        if _progress_cb: _progress_cb(100, "Tamamlandı")
        
        return {
            'ok': True,
            'results': formatted_results,
            'stepCount': len(steps)
        }
    except Exception as e:
        logger.error(f"İş akışı hatası: {e}")
        raise

@app.route('/api/open-folder', methods=['POST'])
def api_open_folder():
    try:
        os.startfile(_out(request.json.get('folder', 'JET_Ciktilari')))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_flask():
    app.run(host='127.0.0.1', port=5757, debug=False,
            use_reloader=False, threaded=True)


if __name__ == '__main__':
    logger.info(f"JET v4.3 | CPU={os.cpu_count()} çekirdek")
    initialize_datalab_formulas()
    try:
        import webview
        threading.Thread(target=run_flask, daemon=True).start()
        time.sleep(1.2)
        webview.create_window('JET Otomasyon Aracı v4.3', 'http://127.0.0.1:5757',
                              width=1280, height=860,
                              min_size=(960, 680), resizable=True)
        webview.start()
    except ImportError:
        threading.Thread(target=run_flask, daemon=True).start()
        time.sleep(1)
        webbrowser.open('http://127.0.0.1:5757')
        logger.info("Tarayıcı: http://127.0.0.1:5757")
        input("Çıkmak için Enter...")
    finally:
        ENGINE.shutdown()
        STORE.cleanup()
