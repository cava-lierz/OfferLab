import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
from .store import Store, AppError
from .jobs import JobRunner
from .engine import Engine, markdown_report
from .provider import DemoProvider, OpenClawProvider, ROOT
from .resume import extract_resume, MAX_BYTES
from .project import import_pr, preview_pdf

load_dotenv(ROOT / '.env', interpolate=False)
MODE = os.getenv('OFFERLAB_MODE', 'demo')
if MODE not in ('demo', 'openclaw'):
    raise RuntimeError('OFFERLAB_MODE must be demo or openclaw')
data_dir = Path(os.getenv('OFFERLAB_DATA_DIR', 'data'))
if not data_dir.is_absolute():
    data_dir = ROOT / data_dir
timeout = min(max(float(os.getenv('OPENCLAW_TIMEOUT', '120')), 5), 150)
report_timeout = min(max(float(os.getenv('OPENCLAW_REPORT_TIMEOUT', '300')), 30), 600)
agent_id = os.getenv('OPENCLAW_AGENT_ID', '').strip()
store = Store(data_dir / 'offerlab.sqlite3')
engine = Engine(store, {'demo': DemoProvider(), 'openclaw': OpenClawProvider(
    os.getenv('OPENCLAW_BASE_URL', 'http://127.0.0.1:18790'), os.getenv('OPENCLAW_TOKEN', ''),
    os.getenv('OPENCLAW_MODEL', 'openclaw'), timeout, agent_id=agent_id, report_timeout=report_timeout)})


@asynccontextmanager
async def lifespan(app):
    runner = JobRunner(engine)
    runner.start()
    try:
        yield
    finally:
        runner.stop()


app = FastAPI(title='OfferLab', version='0.2.0', lifespan=lifespan)


@app.exception_handler(AppError)
async def handle_error(request, exc):
    return JSONResponse(status_code=exc.status, content={'detail': str(exc)})


class CreateInterview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: str | None = Field(default=None, min_length=8, max_length=100)
    practice_focus: str = Field(default='', max_length=4000)
    role: str = Field(min_length=1, max_length=100)
    resume: str = Field(min_length=20, max_length=20000)
    jd: str = Field(default='', max_length=12000)
    main_count: int = Field(default=5, ge=1, le=5, strict=True)


class Answer(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=100)
    question_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=8000)
    excerpt_id: str | None = Field(default=None, min_length=1, max_length=12)


class ImportProject(BaseModel):
    url: str = Field(min_length=1, max_length=400)


class ProjectInterview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    claim: str = Field(min_length=5, max_length=800)
    preview_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    excerpt_ids: list[str] = Field(min_length=1, max_length=3)
    request_id: str = Field(min_length=8, max_length=100)
    target_role: str = Field(default='', max_length=80)
    requirement: str = Field(default='', max_length=500)
    page_notes: dict[str, str] = Field(default_factory=dict, max_length=3)


@app.post('/api/projects/preview')
async def preview_project(body: ImportProject):
    snapshot = await import_pr(body.url)
    await run_in_threadpool(store.save_preview, snapshot)
    return snapshot


@app.post('/api/projects/interviews', status_code=201)
def project_interview(body: ProjectInterview):
    project = store.select_project(body.preview_id, body.excerpt_ids)
    if bool(body.target_role) != bool(body.requirement):
        raise AppError('目标岗位和招聘要求请一起填写。', 422)
    if body.target_role:
        project['target_role'] = body.target_role
    if body.page_notes and (project.get('kind') != 'pdf' or set(body.page_notes) - set(body.excerpt_ids)):
        raise AppError('说明必须对应已选的作品页。', 422)
    for row in project['excerpts']:
        if 'page' in row:
            note = body.page_notes.get(row['id'], '').strip()
            if len(note) > 500 or (not row['code'] and not note):
                raise AppError('图片页需要填写作品说明，每页最多 500 字。', 422)
            if note:
                row['note'] = note
    return engine.create('项目面试 · ' + (body.target_role or project['title'][:85]), body.claim, jd=body.requirement, main_count=1,
                         mode=MODE, request_id=body.request_id, project=project)


@app.post('/api/projects/pdf')
def upload_portfolio(file: UploadFile = File(...)):
    try:
        content = file.file.read(MAX_BYTES + 1)
        snapshot = preview_pdf(file.filename, content)
        store.save_preview(snapshot, content)
        return snapshot
    finally:
        file.file.close()


def pdf_response(owner, scope):
    return Response(store.pdf(owner, scope), media_type='application/pdf', headers={
        'Content-Disposition': 'inline; filename="portfolio.pdf"', 'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "sandbox"})


@app.get('/api/projects/previews/{preview_id}/portfolio.pdf')
def preview_document(preview_id: str):
    return pdf_response(preview_id, 'preview')


@app.get('/api/interviews/{interview_id}/portfolio.pdf')
def interview_document(interview_id: str):
    return pdf_response(interview_id, 'interview')


class AdoptResumeLine(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    previous: str | None = Field(default=None, max_length=500)


@app.post('/api/interviews/{interview_id}/resume-line')
def adopt_resume_line(interview_id: str, body: AdoptResumeLine):
    return engine.adopt_resume_line(interview_id, body.text, body.previous)


class NextQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: str = Field(min_length=1, max_length=100)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': MODE, 'token_configured': bool(os.getenv('OPENCLAW_TOKEN')),
            'gateway_verified': False,
            # Native tools are resolved on the Gateway. Only a run trace confirms availability.
            'retrieval_available': None if MODE == 'openclaw' and agent_id == 'interviewer' else False, 'request_timeout_seconds': timeout,
            'report_timeout_seconds': report_timeout, 'agent_id': agent_id or 'default'}


@app.post('/api/resumes/parse')
def parse_resume(file: UploadFile = File(...)):
    try:
        return {'text': extract_resume(file.filename, file.file.read(MAX_BYTES + 1))}
    finally:
        file.file.close()


@app.get('/api/interviews')
def list_interviews():
    return store.list()


@app.post('/api/interviews', status_code=201)
def create_interview(body: CreateInterview):
    return engine.create(**body.model_dump(), mode=MODE)


@app.get('/api/interviews/{interview_id}')
def get_interview(interview_id: str):
    return store.get(interview_id)


@app.delete('/api/interviews/{interview_id}', status_code=204)
def delete_interview(interview_id: str):
    store.delete(interview_id)
    return Response(status_code=204)


def accepted(state):
    return JSONResponse(status_code=202 if Engine.pending(state) else 200, content=state)


@app.post('/api/interviews/{interview_id}/answers')
def answer(interview_id: str, body: Answer):
    return accepted(engine.submit(interview_id, 'answer', body.model_dump()))


@app.post('/api/interviews/{interview_id}/next')
def next_question(interview_id: str, body: NextQuestion):
    return accepted(engine.submit(interview_id, 'next', body.model_dump()))


@app.post('/api/interviews/{interview_id}/{action}')
def action(interview_id: str, action: str):
    if action not in ('start', 'retry', 'finish'):
        raise AppError('未知操作', 404)
    return accepted(engine.submit(interview_id, action))


@app.get('/api/interviews/{interview_id}/export')
def export(interview_id: str):
    return Response(markdown_report(store.get(interview_id)), media_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="offerlab-report.md"'})
