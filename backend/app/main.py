import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
from .store import Store, AppError
from .jobs import JobRunner
from .engine import Engine, markdown_report
from .provider import DemoProvider, OpenClawProvider, ROOT
from .resume import extract_resume, MAX_BYTES

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
    role: str = Field(min_length=1, max_length=100)
    resume: str = Field(min_length=20, max_length=20000)
    jd: str = Field(default='', max_length=12000)
    main_count: int = Field(default=5, ge=1, le=5, strict=True)


class Answer(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=100)
    question_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=8000)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': MODE, 'token_configured': bool(os.getenv('OPENCLAW_TOKEN')),
            'gateway_verified': False, 'retrieval_available': False, 'request_timeout_seconds': timeout,
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
    state = engine.create(**body.model_dump(), mode=MODE)
    return engine.submit(state['id'], 'retry')


@app.get('/api/interviews/{interview_id}')
def get_interview(interview_id: str):
    return store.get(interview_id)


def accepted(state):
    return JSONResponse(status_code=202 if Engine.pending(state) else 200, content=state)


@app.post('/api/interviews/{interview_id}/answers')
def answer(interview_id: str, body: Answer):
    return accepted(engine.submit(interview_id, 'answer', body.model_dump()))


@app.post('/api/interviews/{interview_id}/{action}')
def action(interview_id: str, action: str):
    if action not in ('start', 'retry', 'finish'):
        raise AppError('未知操作', 404)
    return accepted(engine.submit(interview_id, action))


@app.get('/api/interviews/{interview_id}/export')
def export(interview_id: str):
    return Response(markdown_report(store.get(interview_id)), media_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="offerlab-report.md"'})
