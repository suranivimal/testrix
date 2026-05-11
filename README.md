# Testrix - Autonomous AI Frontend QA Agent

Testrix now supports a full autonomous QA pipeline that acts like a senior QA lead plus frontend QA engineer:

- Reads requirement documents (`.pdf`, `.docx`, `.md`, `.txt`)
- Extracts design baselines from Figma
- Navigates and tests live websites with Playwright (desktop/tablet/mobile)
- Detects functional, UI, responsive, and accessibility issues
- Generates markdown + HTML QA reports
- Produces a release recommendation (`GO` or `NO-GO`)

The existing FastAPI API (`app.py`) remains available. The new autonomous workflow is orchestrated by `main.py`.

## Architecture

New modular structure:

- `agent/` - requirement analyzer, AI reviewer, LLM abstraction
- `browser/` - autonomous Playwright browser agent
- `figma/` - Figma design baseline extraction
- `qa/` - QA evaluation engine and models
- `reports/` - markdown/html report generation
- `prompts/` - reusable review prompts
- `utils/` - logging, retry, file I/O, screenshot manager
- `config/` - environment-driven settings
- `artifacts/` - generated outputs
- `screenshots/` - top-level screenshot storage placeholder

## Setup

```bash
git clone https://github.com/suranivimal/testrix.git
cd testrix
pip install -r requirements.txt
playwright install chromium
```

Copy env template:

```bash
cp .env.example .env
```

Important variables:

- `OPENAI_API_KEY` or `GROQ_API_KEY`
- `LLM_PROVIDER` (`openai` or `groq`)
- `LLM_MODEL`
- `FIGMA_API_TOKEN` (for Figma analysis)
- `REQUIREMENTS_PATH`
- `TARGET_URL`
- `FIGMA_URL` (optional)

## Usage

### Run autonomous QA pipeline

```bash
python main.py --requirements data/sample_requirements.md --url https://example.com --figma-url "https://www.figma.com/design/FILE_KEY/..." --pages / /products /collections/all /cart
```

Strict accessibility gate:

```bash
python main.py --requirements data/sample_requirements.md --url https://example.com --strict-accessibility
```

Visual threshold tuning:

```bash
python main.py --requirements data/sample_requirements.md --url https://example.com --visual-diff-threshold 0.20 --page-visual-threshold /cart=0.15 --page-visual-threshold /products=0.18
```

The command returns structured JSON and writes reports under:

- `artifacts/reports/`
- `artifacts/screenshots/`

Generated reports:

- `bug-report.md`
- `ui-comparison-report.md`
- `responsive-report.md`
- `requirement-coverage.md`
- `qa-summary.md`
- `release-report.md`
- `qa-summary.html`

## Running API Mode (existing)

```bash
uvicorn app:app --reload
```

- UI: `http://localhost:8000/ui/index.html`
- OpenAPI docs: `http://localhost:8000/docs`

## Production Notes

- Restrict `CORS_ORIGINS`
- Add authentication and authorization
- Add persistent job queue for long autonomous runs
- Use CI pipeline to archive artifacts and reports per run

## License

MIT - see `LICENSE`.