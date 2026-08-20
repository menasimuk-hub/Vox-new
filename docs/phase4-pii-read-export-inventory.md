## Phase 4 PII Read/Export Inventory

This is an inventory only for a future field-level encryption pass. No encryption is implemented here.

### Source fields

- `voxbulk-api/app/models/service_order.py`
  - `ServiceOrderRecipient.name`
  - `ServiceOrderRecipient.phone`
  - `ServiceOrderRecipient.email`
  - `ServiceOrderRecipient.result_json`
  - `ServiceOrderRecipient.cv_text`
  - `ServiceOrderRecipient.cv_parsed_json`
- `voxbulk-api/app/models/survey_voice_note_job.py`
  - `audio_file_path`
  - `answer_text`
  - `original_text`
  - `translated_text`

### Dashboard/API read and export surfaces

- `voxbulk-api/app/routers/service_orders.py`
  - interview candidate HTML/PDF reports
  - interview recording proxy
  - interview results CSV/PDF
  - interview batch report detail + CSV export
  - survey voice-note audio download
  - survey results CSV/PDF/XLSX
- `voxbulk-api/app/routers/customer_feedback.py`
  - feedback voice-note audio
  - feedback results CSV/PDF
  - consent events CSV
- `voxbulk-api/app/services/org_data_export_service.py`
  - org DSAR/data-export ZIP

### Service-layer transformations / aggregations

- `voxbulk-api/app/services/interview_candidate_report_export_service.py`
- `voxbulk-api/app/services/interview_report_data_service.py`
- `voxbulk-api/app/services/interview_results_service.py`
- `voxbulk-api/app/services/survey_results_service.py`
- `voxbulk-api/app/services/interview_recording_service.py`
- `voxbulk-api/app/services/customer_feedback/results_service.py`

### Notes for future encryption work

- Route guards now protect the highest-risk service-order export/audio paths, but the underlying stored fields remain plaintext.
- Any future encryption pass must account for:
  - search/filter flows that currently read raw `phone` / `email`
  - exports and report renderers that deserialize `result_json`
  - background jobs that read `audio_file_path` and transcript text
