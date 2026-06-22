#!/usr/bin/env python3
"""
PDF Form Field Mapping — Azure Function (v2 programming model)

Environment variables required:
  AZURE_OPENAI_API_KEY          – your Azure OpenAI key
  AZURE_OPENAI_ENDPOINT         – e.g. https://<resource>.openai.azure.com/
  AZURE_OPENAI_DEPLOYMENT       – deployment name (e.g. gpt-5)
  AZURE_OPENAI_API_VERSION      – e.g. 2025-04-01-preview (GPT-5 needs a 2025 version)
  AZURE_OPENAI_REASONING_EFFORT – optional, default "low" (minimal|low|medium|high)

HTTP GET:
  /api/process?url=<PUBLIC_PDF_URL>[&id=<OPTIONAL_ID>][&debug=true]
"""

import io
import json
import os
import re
import requests
import azure.functions as func
import pdfplumber
from PyPDF2 import PdfReader
from PyPDF2.generic import IndirectObject
from openai import AzureOpenAI

# ---------------------------------------------------------------------------
# Azure OpenAI client
# ---------------------------------------------------------------------------
_client = AzureOpenAI(
    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
)
_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5")

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------
DEFAULT_Y_TOLERANCE = 3.0
DEFAULT_SPACE_GAP   = 12.0

# ---------------------------------------------------------------------------
# Context JSON
# ---------------------------------------------------------------------------
CONTEXT_JSON = {
    "attributesByLevel": {
        "instances": {
            "{166FD}": "Full Name",
            "{F4ED6}": "Maiden Name",
            "{556ED}": "Fictitious Name",
            "{9A604}": "Firm Name",
            "{57EF9}": "State bar no",
            "{76711}": "Address - Street",
            "{6FEB4}": "City",
            "{43D09}": "State",
            "{4CA4D}": "Zip Code",
            "{AD3AF}": "Country",
            "{96127}": "Phone / Telephone",
            "{EF203}": "Fax",
            "{1B072}": "Email ID",
            "{A1588}": "Mailing Address street",
            "{A8EB3}": "Mailing Address City",
            "{8DF7A}": "Mailing Address state",
            "{9E8DF}": "Mailing Address Zip Code",
            "{52900}": "Birth Date",
            "{4B51D}": "Marriage Date",
            "{1226F}": "Age",
            "{B9222}": "Gender",
            "{03D47}": "Occupation",
            "{91068}": "Primary Language",
            "{A298B}": "Height",
            "{75611}": "Weight",
            "{6EAA3}": "Eye color",
            "{54CC9}": "Hair color",
            "{B1BA8}": "Race",
            "{B7D11}": "Marital Status",
            "{E5376}": "Last Name",
            "{8321C}": "First Name",
            "{EB37F}": "Middle Name",
            "{91815}": "New Last Name",
            "{A746F}": "New First Name",
            "{216F7}": "New Middle Name",
            "{9A6DF}": "Drivers license",
            "{AA61C}": "Drivers License State",
            "{94B0F}": "Drivers License expiration date",
            "{5720E}": "Immigration number",
            "{DD5C4}": "Cell Phone",
            "{756BD}": "Home Phone",
            "{34BDC}": "Work Phone",
            "{9A283}": "Alternate Phone",
            "{48FE9}": "Place of Birth",
            "{CDC2F}": "Birth city",
            "{13B4A}": "Birth state",
            "{A7976}": "Nicknames and Aliases",
            "{F8462}": "First Alias",
            "{796DE}": "2nd Alias",
            "{A3BCF}": "3rd Alias",
            "{CE17E}": "Alias, first name",
            "{A66F2}": "Alias, middle name",
            "{615F4}": "Alias, last name",
            "{C6EAC}": "Alias, suffix",
            "{7BF85}": "Arrest name, first",
            "{74F8A}": "Arrest name, middle",
            "{C75B6}": "Arrest name, last",
            "{28921}": "Arrest name, suffix",
            "{E3351}": "Badge number",
            "{C9D97}": "Relation (to contact)",
            "{E6C1C}": "Branch Name"
        },
        "cases": {
            "{2F3F3}": "Case Number",
            "{DD6ED}": "Dept No.",
            "{ADE15}": "Case Name",
            "{D19D1}": "Related Case Number(s)",
            "{E5D74}": "Date of Arrest",
            "{62530}": "Ticket number",
            "{5C43A}": "Civil citation number",
            "{F244F}": "Parking citation number",
            "{FF096}": "Warrant number",
            "{1835C}": "Application number",
            "{89479}": "Agreement number",
            "{9C4F1}": "Date of Offense",
            "{B331E}": "Date of Charge",
            "{A5A8E}": "Probation number",
            "{99F8E}": "Violation(s)",
            "{80227}": "City of arrest",
            "{70B93}": "County of arrest",
            "{46967}": "Police report number",
            "{F7A17}": "Booking number",
            "{C9D92}": "Booking Charges",
            "{6D947}": "Booking date",
            "{53901}": "Booking time",
            "{C9D93}": "Disposition",
            "{C9D94}": "Citation number",
            "{2FEF1}": "Time of Incident",
            "{8551E}": "Date of Incident",
            "{E694D}": "Location of Incident",
            "{C9D95}": "Date of hearing",
            "{C9D96}": "Time of hearing",
            "{9F889}": "Type of hearing",
            "{FCEBF}": "Pretrial date",
            "{784F4}": "Jury trial date",
            "{C49E1}": "Conference time",
            "{67360}": "Deadline date",
            "{46035}": "Real property address (street)",
            "{F0AF3}": "Real property address (city)",
            "{BC8E4}": "Real property address (state)",
            "{4DA39}": "Real property address (zip)",
            "{92A43}": "Division",
            "{CF254}": "Room"
        },
        "both": {
            "{F45D0}": "County",
            "{DD6ED}": "Department",
            "{B587C}": "Unit"
        }
    },
    "groups": [
        {
            "id": "{721E1}",
            "name": "Contacts",
            "instances": [
                "{9D549}", "{8021C}", "{40EB6}", "{6D23E}", "{8D3A9}", "{A313C}", "{18EA6}",
                "{7E41B}", "{376DC}", "{1090B}", "{F64A6}", "{AADD2}", "{6EC71}", "{56198}",
                "{86EEE}", "{61BF1}", "{2E370}", "{81973}", "{1A178}", "{5E8D5}", "{0664C}",
                "{2FF6C}", "{A9192}", "{D4655}", "{9AD91}", "{EB82E}", "{3DC60}", "{DB012}",
                "{20942}", "{4B519}", "{C997A}", "{7E636}", "{1A8EC}", "{84A2B}", "{FD15B}",
                "{AC645}", "{3F90A}", "{656AC}", "{46CD6}", "{D1A1B}", "{35E0E}", "{F1E45}",
                "{7DDAA}", "{D3E6A}", "{4B7B3}", "{B0E20}", "{B3320}", "{3E66B}", "{D796C}",
                "{79CD3}", "{8B564}", "{5F96E}", "{C9ECD}", "{DAE50}", "{2385C}", "{18721}",
                "{B4F4E}", "{F0437}", "{DBBD9}", "{A24ED}", "{C7957}", "{85A82}", "{0D5C5}",
                "{A7C5C}", "{F0FB6}", "{9EAD6}", "{EC3ED}", "{E2A72}", "{D99B2}", "{D2A85}",
                "{69ADE}", "{FD9F7}", "{8B867}", "{BD458}", "{70F77}", "{26305}", "{0E118}",
                "{EFEE3}"
            ]
        }
    ],
    "instances": {
        "{9D549}": "Attorney",
        "{8021C}": "Previous Attorney",
        "{40EB6}": "Client",
        "{6D23E}": "Client's Spouse",
        "{8D3A9}": "Client's Employer",
        "{A313C}": "Plaintiff",
        "{18EA6}": "Plaintiff's Attorney",
        "{7E41B}": "Petitioner",
        "{376DC}": "Attorney for Petitioner",
        "{1090B}": "Petitioner's Spouse",
        "{F64A6}": "Petitioner's Employer",
        "{AADD2}": "Plaintiff/Petitioner",
        "{6EC71}": "Attorney for Plaintiff/Petitioner",
        "{56198}": "Defendant",
        "{86EEE}": "Defendant's Attorney",
        "{61BF1}": "Respondent",
        "{2E370}": "Respondent's Spouse",
        "{81973}": "Respondent's Employer",
        "{1A178}": "Attorney for Respondent",
        "{5E8D5}": "Defendant/Respondent",
        "{0664C}": "Attorney for Defendant/Respondent",
        "{2FF6C}": "Court",
        "{A9192}": "Other Court",
        "{D4655}": "Appellate Court",
        "{9AD91}": "Declarant",
        "{EB82E}": "Agency",
        "{3DC60}": "Agency Representative",
        "{DB012}": "Appellant",
        "{20942}": "Appellant's Attorney",
        "{4B519}": "Applicant",
        "{C997A}": "Conservator",
        "{7E636}": "Conservatee",
        "{1A8EC}": "Conservatee/Ward",
        "{84A2B}": "Ward",
        "{FD15B}": "Gaurdian",
        "{AC645}": "Juvenile",
        "{3F90A}": "Minor",
        "{656AC}": "Obligee",
        "{46CD6}": "Obligor",
        "{D1A1B}": "Officer",
        "{35E0E}": "Owner",
        "{F1E45}": "Party Objecting",
        "{7DDAA}": "Party Providing Notice",
        "{D3E6A}": "Party Requesting",
        "{4B7B3}": "Party Served",
        "{B0E20}": "Party Served (on behalf of)",
        "{B3320}": "Party Submitting",
        "{3E66B}": "Party to Appear",
        "{D796C}": "Party to be Joined",
        "{79CD3}": "Party to be released",
        "{8B564}": "Party to post bond",
        "{5F96E}": "Payee",
        "{C9ECD}": "Payor",
        "{DAE50}": "Person Acknowledging",
        "{2385C}": "Person Authorizing",
        "{18721}": "Person Notified",
        "{B4F4E}": "Person Ordered to Appear",
        "{F0437}": "Person Protected",
        "{DBBD9}": "Person Requesting",
        "{A24ED}": "Person Restrained",
        "{C7957}": "Person Served",
        "{85A82}": "Person Serving",
        "{0D5C5}": "Person Subpoenaed",
        "{A7C5C}": "Person Supported",
        "{F0FB6}": "Person Waiving Notice",
        "{9EAD6}": "Police Department",
        "{EC3ED}": "Prosecutor",
        "{E2A72}": "Prosecuting Agency",
        "{D99B2}": "Provider",
        "{D2A85}": "Purchaser",
        "{69ADE}": "Recipient",
        "{FD9F7}": "Registrant",
        "{8B867}": "Seller",
        "{BD458}": "Sender",
        "{70F77}": "Sheriff",
        "{26305}": "Sheriff's Department",
        "{0E118}": "Sheriff, Marshall or Constable",
        "{EFEE3}": "Spouse"
    }
}

# ---------------------------------------------------------------------------
# Text extraction utilities (unchanged from original)
# ---------------------------------------------------------------------------

def group_phrases_with_coords(word_objs, space_threshold=DEFAULT_SPACE_GAP):
    phrases = []
    current, prev = [], None

    def emit():
        if not current:
            return
        xs   = [w['x0']     for w in current]
        x1s  = [w['x1']     for w in current]
        tops = [w['top']    for w in current]
        bots = [w['bottom'] for w in current]
        txt  = " ".join(w['text'] for w in current)
        x0, x1 = min(xs), max(x1s)
        y_top, y_bot = max(tops), min(bots)
        cx, cy = (x0 + x1) / 2, (y_top + y_bot) / 2
        phrases.append({
            'text': txt, 'x0': x0,
            'top_left': [x0, y_top], 'bottom_right': [x1, y_bot],
            'center': [cx, cy]
        })
        current.clear()

    for w in word_objs:
        gap = (w['x0'] - prev['x1']) if prev else 0
        if prev and gap > space_threshold:
            emit()
        current.append(w)
        t = w['text']
        if (t.endswith((',', ':', ';'))
                or (t.endswith('.') and not t.endswith('.)'))
                or t.endswith('.')):
            emit()
        prev = w
    emit()
    return phrases


def extract_phrases_from_bytes(pdf_bytes, y_tolerance=DEFAULT_Y_TOLERANCE):
    phrases, pid = [], 1
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pnum, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                x_tolerance=1, y_tolerance=y_tolerance,
                keep_blank_chars=False, use_text_flow=True
            )
            words_sorted = sorted(words, key=lambda w: (w['top'], w['x0']))
            lines, curr_top, curr_line = [], None, []
            for w in words_sorted:
                if curr_top is None or abs(w['top'] - curr_top) > y_tolerance:
                    if curr_line:
                        lines.append(curr_line)
                    curr_line, curr_top = [w], w['top']
                else:
                    curr_line.append(w)
            if curr_line:
                lines.append(curr_line)
            for word_objs in lines:
                sorted_objs = sorted(word_objs, key=lambda w: w['x0'])
                for grp in group_phrases_with_coords(sorted_objs):
                    phrases.append({
                        'id': pid, 'page': pnum, 'line': None,
                        'text': grp['text'],
                        'top_left': grp['top_left'],
                        'bottom_right': grp['bottom_right'],
                        'center': grp['center']
                    })
                    pid += 1
    return phrases


def extract_fields_from_bytes(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_height = pdf.pages[0].height
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_ref_map = {}
    for idx, pg in enumerate(reader.pages, start=1):
        ref = getattr(pg, 'indirect_reference', None)
        if isinstance(ref, IndirectObject):
            page_ref_map[(ref.idnum, ref.generation)] = idx
    root = reader.trailer.get('/Root')
    if isinstance(root, IndirectObject):
        root = root.get_object()
    acro = root.get('/AcroForm', {})
    if isinstance(acro, IndirectObject):
        acro = acro.get_object()
    raw_fields = acro.get('/Fields', [])
    fields = []

    def recurse(flds, parent=''):
        for f in flds:
            if isinstance(f, IndirectObject):
                f = f.get_object()
            nm = f.get('/T')
            full_name = f"{parent}.{nm}" if parent and nm else (nm or parent or '')
            kids = f.get('/Kids')
            if kids:
                recurse(
                    [k.get_object() if isinstance(k, IndirectObject) else k for k in kids],
                    full_name
                )
            else:
                ft = f.get('/FT')
                Ff = int(f.get('/Ff') or 0)
                if ft == '/Tx':
                    type_out = 'Multiline' if (Ff & 4096) else 'Text'
                elif ft == '/Btn':
                    type_out = ('PushButton' if Ff & 65536 else
                                'Radio'      if Ff & 32768 else 'Checkbox')
                elif ft == '/Ch':
                    type_out = 'Choice'
                elif ft == '/Sig':
                    type_out = 'Signature'
                else:
                    type_out = 'Unknown'
                rect = f.get('/Rect', [])
                if len(rect) == 4:
                    x0, y0, x1, y1 = [float(v) for v in rect]
                    tl = [x0, page_height - y1]
                    br = [x1, page_height - y0]
                    cx, cy = (tl[0] + br[0]) / 2, (tl[1] + br[1]) / 2
                else:
                    tl = br = None; cx = cy = None
                pkey = f.get('/P')
                pg_num = None
                if isinstance(pkey, IndirectObject):
                    pg_num = page_ref_map.get((pkey.idnum, pkey.generation))
                fields.append({
                    'name': full_name, 'type': type_out,
                    'top_left': tl, 'bottom_right': br,
                    'center': [cx, cy], 'page': pg_num,
                    'line': None, 'label_id': None, 'label': None
                })

    recurse(raw_fields)
    return fields


def assign_labels_and_lines(fields, phrases, y_tol=DEFAULT_Y_TOLERANCE):
    page_positions = {}
    for ph in phrases:
        page_positions.setdefault(ph['page'], set()).add(ph['center'][1])
    for fld in fields:
        center = fld.get('center')
        if fld['page'] and center and center[1] is not None:
            page_positions.setdefault(fld['page'], set()).add(center[1])
    page_line_map = {}
    for page, ypos in page_positions.items():
        ys = sorted(ypos)
        clusters = []
        for y in ys:
            if not clusters or y - clusters[-1][0] > y_tol:
                clusters.append([y])
            else:
                clusters[-1].append(y)
        mapping = {y: idx + 1 for idx, cluster in enumerate(clusters) for y in cluster}
        page_line_map[page] = mapping

    for ph in phrases:
        ph['line'] = page_line_map.get(ph['page'], {}).get(ph['center'][1])
    for fld in fields:
        center = fld.get('center')
        if fld['page'] and center and center[1] is not None:
            fld['line'] = page_line_map.get(fld['page'], {}).get(center[1])

    for fld in fields:
        if fld['type'] in ('Checkbox', 'Radio') and fld['page'] and fld['line'] and fld.get('bottom_right'):
            brx = fld['bottom_right'][0]
            cands = [ph for ph in phrases
                     if ph['page'] == fld['page'] and ph['line'] == fld['line']
                     and ph['center'][0] > brx]
            if cands:
                label = min(cands, key=lambda ph: ph['center'][0] - brx)
                fld['label_id'], fld['label'] = label['id'], label['text']

    for fld in fields:
        if fld['type'] in ('Text', 'Multiline') and fld['page'] and fld['line'] and fld.get('top_left'):
            fx, fy = fld['top_left']
            same_line = [ph for ph in phrases
                         if ph['page'] == fld['page'] and ph['line'] == fld['line']]
            close = []
            for ph in same_line:
                prx = ph['bottom_right'][0]; pry = ph['top_left'][1]
                if abs(pry - fy) <= y_tol and abs(prx - fx) <= DEFAULT_SPACE_GAP:
                    close.append(ph)
            if close:
                label = max(close, key=lambda p: p['bottom_right'][0])
                fld['label_id'], fld['label'] = label['id'], label['text']

    for fld in fields:
        if (fld['type'] in ('Text', 'Multiline') and fld.get('label_id') is None
                and fld['page'] and fld['line'] and fld.get('top_left')):
            fx, fy = fld['top_left']; ln = fld['line']; pg = fld['page']
            for target in (ln - 1, ln + 1):
                if target > 0:
                    cands = [ph for ph in phrases if ph['page'] == pg and ph['line'] == target]
                    if cands:
                        if target == ln + 1:
                            cands = [ph for ph in cands if abs(ph['center'][1] - fy) <= 4]
                        if cands:
                            label = min(cands, key=lambda p: abs(p['center'][0] - fx))
                            fld['label_id'], fld['label'] = label['id'], label['text']
                            break

    for fld in fields:
        lid = fld.get('label_id')
        if lid is not None:
            match = next((p for p in phrases if p['id'] == lid), None)
            if match and match.get('line') is not None:
                fld['line'] = match['line']

    fields.sort(key=lambda f: (
        f['page']        or float('inf'),
        f['line']        or float('inf'),
        f['center'][0]   or float('inf')
    ))


def write_text_from_phrases_to_string(phrases, fields):
    buf = io.StringIO()
    pages = {}
    for ph in phrases:
        pages.setdefault(ph['page'], {}).setdefault(ph['line'], []).append(ph)
    for pg in sorted(pages):
        buf.write(f"--- Page {pg} ---\n")
        lines = sorted(pages[pg].keys())
        for ln in range(lines[0], lines[-1] + 1):
            if ln in pages[pg]:
                row = sorted(pages[pg][ln], key=lambda p: p['center'][0])
                texts = []
                for ph in row:
                    text = ph['text']
                    labs = [fld for fld in fields if fld.get('label_id') == ph['id']]
                    for fld in labs:
                        placeholder = '{' + fld['name'] + '}'
                        text = (placeholder + ' ' + text
                                if fld['type'] in ('Checkbox', 'Radio')
                                else text + ' ' + placeholder)
                    texts.append(text)
                buf.write(" ".join(texts) + "\n")
            else:
                fls = [fld for fld in fields if fld['page'] == pg and fld['line'] == ln]
                if fls:
                    phs = ['{' + fld['name'] + '}' for fld in sorted(fls, key=lambda f: f['center'][0] or 0)]
                    buf.write(" ".join(phs) + "\n")
                else:
                    buf.write("\n")
        buf.write("\n")
    return buf.getvalue()

# ---------------------------------------------------------------------------
# Azure OpenAI mapping (replaces map_fields_with_openai)
# ---------------------------------------------------------------------------

def map_fields_with_azure_openai(text_output, fields_geo, phrases_geo):
    system_instructions = (
        "You are an AI assistant for SuperDocs.com, specialized in mapping court-form fields to database attributes.\n\n"
        "For each form field, you must return exactly one JSON object with four string keys:\n"
        "  • name       – the PDF field identifier (e.g. \"FORM[0].Page1…AttyName_ft[0]\")\n"
        "  • group      – the contact group ID (e.g. \"{721E1}\") or empty string\n"
        "  • instance   – the contact instance ID (e.g. \"{9D549}\") or empty string\n"
        "  • expression – one or more attribute IDs (e.g. \"{166FD}\") or blank, sometimes with text or formatting around them.\n"
        "                 attributes are swapped out with data, like a mail merge, so city, state zip would be {6FEB4}, {43D09} {4CA4D}\n"
        "                 to have proper punctuation and spacing between the data.\n\n"
        "INPUT FORMAT — you receive THREE views of ONE court form:\n"
        "  (1) TEXT: a readable rendering of the form. It is APPROXIMATE — field placeholders embedded in it\n"
        "      are positioned by a heuristic and are frequently WRONG. Use TEXT only for semantic context and\n"
        "      reading order. NEVER decide a field's label from where its placeholder appears in TEXT.\n"
        "  (2) PHRASES: every visible text snippet with its bounding box.\n"
        "  (3) FIELDS: every fillable field with its bounding box, type, size (lines), and an `approx_label`\n"
        "      that is a heuristic guess and is OFTEN WRONG — do not trust it; verify with geometry.\n\n"
        "COORDINATES & LABEL ASSOCIATION (this is the authoritative method):\n"
        "  - Every box is [x0, y0, x1, y1] in PDF points (72/inch). Origin is the page TOP-LEFT; x grows to the\n"
        "    RIGHT, y grows DOWNWARD. So smaller y = higher on the page.\n"
        "  - A phrase is on the SAME ROW as a field when their vertical extents overlap (e.g. the phrase's\n"
        "    vertical center lies between the field's y0 and y1, or vice-versa). Field boxes are often taller\n"
        "    than their label text, so do NOT require their top edges to match.\n"
        "  - To find a field's label:\n"
        "      a. FIRST choose the phrase on the same row whose right edge (x1) is at or just left of the field's\n"
        "         left edge (x0) and closest to it — i.e. the caption immediately preceding the field. Captions\n"
        "         usually end with ':'.\n"
        "      b. If there is none on the row, use the nearest phrase directly ABOVE the field (smaller y) whose\n"
        "         x-range overlaps the field.\n"
        "      c. IGNORE distant phrases, page headers/footers, and form codes (e.g. 'EJ-130', 'MC-012').\n"
        "  - Worked example of the failure to avoid: a field at [259,44,366,57] with caption 'STATE BAR NO.:' at\n"
        "    [209,49,257,55] (right edge 257, just left of 259, rows overlap) takes that caption — NOT a form\n"
        "    code like 'EJ-130' sitting far away at the top-right corner.\n\n"
        "Mapping rules:\n"
        "  1. **Contacts**\n"
        "     - If a field pertains to a person or court (attorney, client, court), set `group` to the Contacts group ID.\n"
        "     - Set `instance` according to the role (e.g. Attorney, Client, Court).\n"
        "     - In `expression`, include the one or more attribute IDs (e.g. Full Name, Bar Number, Address).\n"
        "  2. **Case-level data**\n"
        "     - If a field is about the case itself (case number, case name), leave `group` and `instance` blank.\n"
        "     - Put the case attribute ID(s) in `expression`.\n"
        "  3. **Multiline fields**\n"
        "     - If a field spans multiple lines, you may format multiple attribute IDs up to the field's `size` (number of lines).\n"
        "     - Drop the lowest-priority line if there isn't enough room.\n"
        "  4. **General guidance**\n"
        "     - Always prefer Full Name (`{166FD}`) over splitting first/last, unless the label specifies otherwise.\n"
        "     - Distinguish a PERSON's name from an ORGANIZATION's name. A field labeled 'Firm Name',\n"
        "       'Law Firm', 'Firm', 'Attorney's Firm', or any company/office/agency name maps to the\n"
        "       Firm Name attribute (`{9A604}`) — NOT Full Name. A field for a person (e.g. 'Attorney',\n"
        "       'Name of Attorney', 'Attorney for ...', or a party/contact's name) maps to Full Name\n"
        "       (`{166FD}`) under that person's instance. Never map a firm/organization field to Full Name.\n"
        "     - Internal field names that are nearly identical (e.g. 'TextField29' vs 'TextField292', or\n"
        "       names differing only by a trailing index) are DIFFERENT fields. Map each strictly by its\n"
        "       own geometry/label — do not copy a neighbor's mapping onto a similarly-named field.\n"
        "     - Also consider the internal field name as a weak secondary hint; it can even CONTRADICT the\n"
        "       visible label (e.g. a field internally named 'Defendant' sitting under a 'PLAINTIFF/PETITIONER:'\n"
        "       caption). When they conflict, the visible caption wins.\n"
        "     - All forms are completed by attorneys or their firms.\n"
        "     - Be aware of the context of the form as a whole.\n"
        "     - Consistency: once you assign a group+instance for a given role, apply that same mapping to all other fields for that role.\n"
        "     - Omit any field you cannot confidently map.\n"
        "     - DO NOT USE any group, instance or attribute not provided to you in the Context JSON.\n\n"
        "You have access to a fixed Context JSON (attributes, groups, instances). You must not reference fields outside of that context.\n\n"
        "Respond **only** with a single JSON object matching this exact schema:\n"
        "{\n"
        "  \"mappedFields\": [ { name, group, instance, expression }, … ]\n"
        "}\n\n"
        f"Context JSON:\n{json.dumps(CONTEXT_JSON, indent=2)}"
    )

    user_prompt = (
        "TEXT (approximate; for semantic context only — do NOT infer labels from placeholder positions here):\n"
        f"{text_output}\n\n"
        "PHRASES — visible text with boxes [x0,y0,x1,y1], grouped per page:\n"
        f"{json.dumps(phrases_geo, separators=(',', ':'))}\n\n"
        "FIELDS — fillable fields with box [x0,y0,x1,y1], type, size (lines), and a fallible approx_label:\n"
        f"{json.dumps(fields_geo, separators=(',', ':'))}\n\n"
        "For each field, determine its true caption from the COORDINATES (per the rules above), then apply the "
        "mapping rules. Return **only** the JSON object described."
    )

    # GPT-5 (and other reasoning models) only accept the default temperature,
    # so we omit it. response_format forces valid JSON; reasoning_effort is kept
    # low because field mapping is structured extraction rather than open-ended
    # reasoning, which keeps latency and token cost down.
    resp = _client.chat.completions.create(
        model=_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_instructions},
            {"role": "user",   "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        reasoning_effort=os.environ.get("AZURE_OPENAI_REASONING_EFFORT", "low"),
    )

    payload = json.loads(resp.choices[0].message.content)
    return payload.get("mappedFields", [])

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_model_inputs(pdf_bytes):
    """Run extraction + label assignment and return exactly what the model sees:
    the text representation of the form and the per-field list (name/type/label/size).
    Exposed separately so it can be inspected (dump mode) without an LLM call."""
    phrases = extract_phrases_from_bytes(pdf_bytes, DEFAULT_Y_TOLERANCE)
    fields  = extract_fields_from_bytes(pdf_bytes)
    assign_labels_and_lines(fields, phrases, DEFAULT_Y_TOLERANCE)
    text_out = write_text_from_phrases_to_string(phrases, fields)
    minimal = []
    for fld in fields:
        entry = {'name': fld['name'], 'type': fld['type'], 'label': fld['label']}
        if fld['type'] == 'Multiline' and fld.get('top_left'):
            h = abs(fld['bottom_right'][1] - fld['top_left'][1])
            entry['size'] = max(1, int(round(h / 12)))
        else:
            entry['size'] = 1
        minimal.append(entry)
    return text_out, minimal, phrases, fields


def _round_box(o):
    """Return a field/phrase bounding box as [x0, y0, x1, y1] integers, or None."""
    tl, br = o.get('top_left'), o.get('bottom_right')
    if not tl or not br or tl[0] is None or br[0] is None:
        return None
    return [round(tl[0]), round(tl[1]), round(br[0]), round(br[1])]


def process_pdf_stream(pdf_bytes):
    text_out, minimal, phrases, fields = build_model_inputs(pdf_bytes)

    # Authoritative geometry the model uses to associate captions with fields.
    phrases_geo = [
        {'page': ph['page'], 'text': ph['text'], 'box': _round_box(ph)}
        for ph in phrases if _round_box(ph)
    ]
    fields_geo = []
    for fld, m in zip(fields, minimal):
        fields_geo.append({
            'name': fld['name'],
            'type': fld['type'],
            'page': fld['page'],
            'size': m['size'],
            'box': _round_box(fld),
            'approx_label': fld.get('label'),
        })

    return map_fields_with_azure_openai(text_out, fields_geo, phrases_geo)

# ---------------------------------------------------------------------------
# Azure Function app
# ---------------------------------------------------------------------------

app = func.FunctionApp()

@app.route(route="process", methods=["GET"])
def process(req: func.HttpRequest) -> func.HttpResponse:
    url         = req.params.get('url')
    id_param    = req.params.get('id')
    debug_param = req.params.get('debug', '').lower()
    dump_param  = req.params.get('dump', '').lower()

    if not url:
        return func.HttpResponse(
            json.dumps({'error': "Missing 'url' query parameter"}),
            status_code=400, mimetype="application/json"
        )

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        return func.HttpResponse(
            json.dumps({'error': f'Failed to download PDF: {e}'}),
            status_code=400, mimetype="application/json"
        )

    # Diagnostic mode: return the exact text + field/label inputs the model would
    # receive, WITHOUT calling the LLM. Use to inspect label-assignment quality.
    if dump_param == 'true':
        try:
            text_out, minimal, phrases, fields = build_model_inputs(pdf_bytes)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({'error': f'Processing error: {e}'}),
                status_code=500, mimetype="application/json"
            )
        resp = {'text': text_out, 'fields': minimal}
        # coords=true adds raw geometry for one page so label-binding can be
        # inspected: each phrase box and each field rect (page-space, y-down).
        if req.params.get('coords', '').lower() == 'true':
            try:
                page = int(req.params.get('page', '1') or 1)
            except ValueError:
                page = 1
            resp['page'] = page
            resp['phrases'] = [
                {'id': p['id'], 'line': p['line'], 'text': p['text'],
                 'top_left': p['top_left'], 'bottom_right': p['bottom_right'], 'center': p['center']}
                for p in phrases if p['page'] == page
            ]
            resp['fields_detail'] = [
                {'name': f['name'], 'type': f['type'], 'line': f['line'],
                 'top_left': f['top_left'], 'bottom_right': f['bottom_right'], 'center': f['center'],
                 'label_id': f.get('label_id'), 'label': f['label']}
                for f in fields if f['page'] == page
            ]
        return func.HttpResponse(
            json.dumps(resp, indent=2),
            mimetype="application/json"
        )

    try:
        mapped = process_pdf_stream(pdf_bytes)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({'error': f'Processing error: {e}'}),
            status_code=500, mimetype="application/json"
        )

    if debug_param == 'true':
        attr_map = {}
        for level_dict in CONTEXT_JSON['attributesByLevel'].values():
            attr_map.update(level_dict)
        group_map    = {grp['id']: grp['name'] for grp in CONTEXT_JSON.get('groups', [])}
        instance_map = CONTEXT_JSON.get('instances', {})

        for obj in mapped:
            ids = re.findall(r'\{[0-9A-F]+\}', obj.get('expression', ''))
            obj['expression_names'] = [attr_map.get(i, '') for i in ids]
            obj['group_name']       = group_map.get(obj.get('group', ''), '')
            obj['instance_name']    = instance_map.get(obj.get('instance', ''), '')

    result = {id_param: mapped} if id_param else mapped
    return func.HttpResponse(json.dumps(result), mimetype="application/json")
