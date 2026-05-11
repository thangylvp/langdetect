# langdetect

Vietnamese / English language detector for the conversational-AI gateway.
Two generations of detector live side-by-side in the repo:

| Folder | Generation | Approach |
|---|---|---|
| top level (`detector.py`, `service.py`, `router.py`, …) | **v1** | Lingua / FastText library wrappers, single-confidence threshold |
| [`v2/`](v2/) | **v2** | Rule-based pipeline driven by the 4 quy tắc in [`v2/task_requirement.md`](v2/task_requirement.md), using `underthesea` POS+NER as the open-class classifier |

## v2 — current focus

```
v2/
├── phuluc.md            ← Phụ lục A: Bảng 1–4
├── task_requirement.md  ← spec: Quy tắc 1–4
└── src/
    ├── rule_detector.py     ← pipeline (Rule 4 → Rule 3 → Rule 1 → Rule 2)
    ├── cultural_terms.py    ← VN cultural common nouns underthesea mis-tags as N
    ├── en_anchors.py        ← bounded Table 4 of English sentence-initial anchors
    ├── test_rule_detector.py
    └── evaluate.py          ← CSV-driven evaluation harness
```

### Setup

```bash
conda activate langdetect           # or any Python 3.11 env
pip install underthesea pytest
```

### Run unit tests

```bash
cd v2/src && python -m pytest test_rule_detector.py -v
```

### Evaluate against a labelled CSV

```bash
cd v2/src
python evaluate.py [INPUT_CSV] [-o OUTPUT_CSV]
```

- Default input: `../../Result_LIB_language_*.csv` at the repo root
- Default output: `../results/eval_<input-stem>_<timestamp>.csv`
- The script auto-detects the input column (`VA_SAMPLE` / `input` / `text` / …)
  and the ground-truth column (`GT_language` / `ground_truth` / `label` / …)

Latest run (7 917 rows): **99.18 %** overall, 99.30 % on `vi`, 94.18 % on `en`.
See [v2/results/](v2/results/) for the per-row breakdown.
