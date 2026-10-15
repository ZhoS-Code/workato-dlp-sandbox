"""Fail-closed demo inspector. Not a certified enterprise DLP engine."""
import base64
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from pypdf import PdfReader
from docx import Document
from pptx import Presentation
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / 'policy.json').read_text())

class UnsafeToInspect(Exception):
    pass


def _office_container(blob, kind):
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
        names = z.namelist()
        if len(names) > 1000:
            raise UnsafeToInspect('TOO_MANY_PARTS')
        for name in names:
            n = name.lower()
            if any(x in n for x in ('vbaproject', '/embeddings/', '/externallinks/', '/activex/', '/media/')):
                raise UnsafeToInspect('UNINSPECTED_EMBEDDED_CONTENT')
            if name.endswith('.rels'):
                val = z.read(name)
                if b'TargetMode="External"' in val or b"TargetMode='External'" in val:
                    raise UnsafeToInspect('EXTERNAL_RELATIONSHIP')
        expected = {'docx':'word/document.xml','xlsx':'xl/workbook.xml','pptx':'ppt/presentation.xml'}[kind]
        if expected not in names:
            raise UnsafeToInspect('BAD_OFFICE_CONTAINER')
    except (zipfile.BadZipFile, RuntimeError, ValueError, KeyError):
        raise UnsafeToInspect('INVALID_OFFICE_FILE')


def extract(data, extension):
    if extension in ('.txt', '.csv', '.json'):
        try:
            s = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise UnsafeToInspect('INVALID_UTF8')
        if extension == '.json':
            try:
                json.loads(s)
            except json.JSONDecodeError:
                raise UnsafeToInspect('INVALID_JSON')
        if extension == '.csv':
            list(csv.reader(io.StringIO(s), strict=True))
        return s
    if extension == '.pdf':
        try:
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise UnsafeToInspect('ENCRYPTED_PDF')
            if not reader.pages:
                raise UnsafeToInspect('EMPTY_PDF')
            pages=[]
            for page in reader.pages:
                if '/Annots' in page or '/XObject' in page.get('/Resources', {}):
                    raise UnsafeToInspect('UNINSPECTED_PDF_OBJECTS')
                s = page.extract_text() or ''
                if not s.strip():
                    raise UnsafeToInspect('NON_TEXT_PDF_PAGE')
                pages.append(s)
            return '\n'.join(pages)
        except UnsafeToInspect:
            raise
        except Exception:
            raise UnsafeToInspect('PDF_EXTRACTION_FAILED')
    if extension in ('.docx','.xlsx','.pptx'):
        _office_container(data, extension[1:])
    try:
        if extension == '.docx':
            d=Document(io.BytesIO(data))
            # NOTE: includes headers/footers, paragraphs, tables. Block other unsupported structures via OOXML check below.
            pieces=[p.text for p in d.paragraphs]
            for t in d.tables:
                for row in t.rows:
                    pieces.extend(c.text for c in row.cells)
            for sec in d.sections:
                for hf in (sec.header, sec.footer):
                    pieces.extend(p.text for p in hf.paragraphs)
            _reject_unsupported_xml(data, '.docx')
            return '\n'.join(pieces)
        if extension == '.xlsx':
            wb=load_workbook(io.BytesIO(data), read_only=False, data_only=False)
            chunks=[]
            for ws in wb.worksheets:
                if ws._images or ws._charts:
                    raise UnsafeToInspect('UNINSPECTED_WORKBOOK_DRAWINGS')
                for row in ws.iter_rows():
                    for cell in row:
                        if cell.data_type == 'f':
                            raise UnsafeToInspect('FORMULA_NOT_EVALUATED')
                        if cell.comment:
                            chunks.append(str(cell.comment.text))
                        if cell.value is not None:
                            chunks.append(str(cell.value))
            _reject_unsupported_xml(data, '.xlsx')
            return '\n'.join(chunks)
        if extension == '.pptx':
            p=Presentation(io.BytesIO(data))
            chunks=[]
            for slide in p.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        chunks.append(shape.text)
                    if shape.has_table:
                        for row in shape.table.rows:
                            chunks.extend(c.text for c in row.cells)
                if slide.has_notes_slide:
                    chunks.append(slide.notes_slide.notes_text_frame.text)
            _reject_unsupported_xml(data, '.pptx')
            return '\n'.join(chunks)
    except UnsafeToInspect:
        raise
    except Exception:
        raise UnsafeToInspect('OFFICE_EXTRACTION_FAILED')
    raise UnsafeToInspect('UNSUPPORTED_TYPE')


def _reject_unsupported_xml(data, ext):
    # Conservative sandbox: block advanced OOXML features we don't comprehensively parse.
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=z.namelist()
        for n in names:
            lower=n.lower()
            if (ext == '.docx' and ('footnotes.xml' in lower or 'endnotes.xml' in lower or '/comments' in lower)) or (ext == '.pptx' and ('comments' in lower or 'charts/' in lower or 'diagrams/' in lower)) or (ext == '.xlsx' and ('pivot' in lower or 'charts/' in lower or 'drawings/' in lower)):
                raise UnsafeToInspect('UNINSPECTED_ADVANCED_FEATURE')
        if ext == '.docx':
            # Shapes/text boxes, tracked revisions may carry text we aren't reliably extracting.
            for n in names:
                if n.startswith('word/') and n.endswith('.xml'):
                    v=z.read(n)
                    if any(x in v for x in (b'<w:ins',b'<w:del',b'<w:txbxContent',b'<wps:txbx', b'<w:altChunk')):
                        raise UnsafeToInspect('UNINSPECTED_WORD_CONTENT')


def inspect(file_name, data, request_id='local'):
    response={'decision':'BLOCK','file_name':Path(file_name).name,'policy_version':POLICY['version'],
              'reason_code':'INSPECTION_FAILED','request_id':str(request_id)}
    ext=Path(file_name).suffix.lower()
    if not data:
        response['reason_code']='EMPTY_FILE'; return response
    if len(data)>POLICY['max_bytes']:
        response['reason_code']='FILE_TOO_LARGE'; return response
    if ext not in POLICY['allow_extensions']:
        response['reason_code']='UNSUPPORTED_TYPE'; return response
    # Signature checks prevent basic extension spoofing.
    if ext=='.pdf' and not data.startswith(b'%PDF-'):
        response['reason_code']='FILE_TYPE_MISMATCH'; return response
    if ext in ('.docx','.xlsx','.pptx') and not data.startswith(b'PK'):
        response['reason_code']='FILE_TYPE_MISMATCH'; return response
    try:
        content=extract(data, ext)
        if not content.strip():
            raise UnsafeToInspect('NO_INSPECTABLE_TEXT')
        for rule in POLICY['deny_patterns']:
            if re.search(rule['regex'],content):
                response['reason_code']='POLICY_VIOLATION'
                response['matched_rule_ids']=[rule['id']]
                return response
        response['decision']='ALLOW'; response['reason_code']='POLICY_COMPLIANT'
    except UnsafeToInspect as e:
        response['reason_code']=str(e)
    except Exception:
        response['reason_code']='INSPECTION_FAILED'
    return response

if __name__=='__main__':
    if len(sys.argv)<2:
        raise SystemExit('usage: python inspector.py PATH')
    p=Path(sys.argv[1]); print(json.dumps(inspect(p.name,p.read_bytes()),indent=2))
