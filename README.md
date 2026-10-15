# Workato-to-Claude file governance: runnable DEMO

**This is a sandbox, not production-grade DLP.** The policy is fictional. No Claude upload occurs in this codebase. Nothing connects to your Workato workspace automatically. A Claude Desktop tool/connector is not capable of preventing other direct attachments to Claude Desktop.

## Scope

- Decisions: **ALLOW** or **BLOCK** only.
- Supported for limited local inspection: UTF-8 `.txt`, `.csv`, `.json`, machine-readable simple `.pdf`, simple `.docx`, `.xlsx`, `.pptx`.
- Default BLOCK: images, scanned PDFs, `.xls`, `.zip`, unsupported document features, formulas, macros, encrypted files, hidden embedded objects, extraction errors.
- A passing result means only that this *demo* detected no configured patterns in extractable content. It is **not** evidence that data is safe to disclose.
- PDF policy is meant to be translated by a policy owner into reviewed structured `policy.json`; do not allow arbitrary PDF prose to control enforcement directly.

## Local demonstration

```bash
pip install -r requirements.txt
python inspector.py samples/public.txt
python inspector.py samples/restricted.csv
python inspector.py samples/public.pdf
python inspector.py samples/restricted.docx
python inspector.py samples/restricted.xlsx
python inspector.py samples/public.pptx
python -m unittest discover -s tests -v
```

### Optional local HTTP adapter

```bash
export INSPECTOR_TOKEN='choose-a-long-random-value'
uvicorn api:app --host 127.0.0.1 --port 8080
```

POST to `http://127.0.0.1:8080/inspect` with `x-inspector-token`, JSON `file_name`, `file_base64`, `request_id`. Use private TLS networking and secure credential management for any non-local deployment; **do not expose this example service or log file content publicly**.

## Workato recipe blueprint (not an importable recipe export)

### A. Policy management
1. Store a **company-approved** PDF policy in a restricted managed location.
2. On controlled policy updates, extract machine-readable text with suitable PDF extractor (OCR under an approved boundary if scanned).
3. Map PDF clauses into explicit rule IDs, conditions, actions and precedence.
4. Have a policy owner approve the generated JSON; validate and version it. Publish only after tested; rollback on failure.
5. Apply updates to your inspector through approved CI/deployment, not by runtime uncontrolled AI rewriting rules.

### B. File inspection
1. `Recipe Functions > New function call trigger`: `file_name` (string), `file_base64` (string), `request_id` (string); output `decision`, `reason_code`, `policy_version`, `file_name`, `request_id`.
2. `HTTP > Send request`: POST to a **privately deployed**, authenticated inspector `/inspect`; header `x-inspector-token` from secure connection settings; body maps 3 function inputs.
3. Validate inspector response, fail closed if unavailable, timed out, malformed, or `decision` is anything other than literal `ALLOW`.
4. Return one of two states to caller, with non-sensitive reason code and request id.

### C. Workato API Gateway (existing recipe)
1. `API Platform > New API request` with JSON request body matching `workato/request_schema.json`.
2. Call Recipe Function B **synchronously** and get decision. Map `file_name`, `file_base64`, `request_id`.
3. `IF decision == "ALLOW"` THEN return allow response. **Only in a separate controlled upload/release action** can the approved file be forwarded to a company-approved Claude API route.
4. `ELSE` return `BLOCK`, and do not forward the file. On job/error handler failure, return `BLOCK`.
5. Use `API Platform > Respond to API request` in appropriate branches; response is terminal, so don't place actions after response expecting them to execute.
6. Configure API client authentication, least-privilege access, throughput limits, payload limits, retention and sensitive-data masking. Restrict direct bypass routes operationally.

### Example JSON input

```json
{"file_name":"public.txt","file_base64":"SGVsbG8gd29ybGQh","request_id":"sandbox-01"}
```

### Security / accuracy gaps before production

* Rules do not cover every form of PII, context-based confidentiality, obfuscation, cross-file inference, metadata, comments, alt text, images or every format feature.
* Do not upload restricted employee files to third-party LLMs for inspection; choose approved processing boundary.
* Real Office files can conceal non-text content; only a formally validated extraction pipeline with malware scanning and file-type identification should release them.
* Strong assurance requires comprehensive extraction, OCR, data classification, adversarial test set, human policy approval, audit, retention controls, access controls and third-party pen test.
* The current sandbox local API gives a decision only; it **does not upload** to Claude or enforce restrictions on the independent Claude Desktop attach button.
