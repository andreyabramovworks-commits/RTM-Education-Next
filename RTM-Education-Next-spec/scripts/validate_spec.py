#!/usr/bin/env python3
"""Validate RTM-Education-Next specification files, IDs, Markdown links and critical decisions.

Requirements traceability: REQ-192
"""
from pathlib import Path
import re, hashlib, sys, zipfile
ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs'
REQUIRED=[
    'README.md','AGENTS.md','references/AGENTS.original.md',
    'docs/НАЧАТЬ-ЗДЕСЬ.md','docs/CURRENT_MVP_BASELINE.md',
    'docs/VISUAL_DESIGN_WORKSTREAM.md','docs/CHANGELOG.md','docs/DECISIONS.md',
    'docs/REQUIREMENTS_TRACEABILITY.md','docs/ARCHITECTURE.md','docs/DATA_MODEL.md',
    'docs/ERD.md','docs/CONTENT_REVISIONS.md','docs/ACCESS_AND_ROLES.md',
    'docs/COURSES_EDITOR_UI.md','docs/KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md',
    'docs/COURSE_ASSIGNMENTS.md','docs/REVIEW_CENTER_NEXT.md',
    'docs/TEST_REVIEW_WORKFLOWS.md','docs/UI_NAVIGATION.md',
    'docs/MVP_CONTRACT.md','docs/OPEN_QUESTIONS.md','docs/WORK_PLAN.md',
    'docs/QUALITY_AND_TEST_MATRIX.md','docs/LEGACY_SOURCE_INVENTORY.md',
    'docs/WORK_HANDOFF_PROMPT.md','scripts/validate_spec.py'
]
errors=[]
for file in REQUIRED:
    p=ROOT/file
    if not p.is_file():errors.append('Missing required: '+file)
    elif p.stat().st_size<80:errors.append('Suspiciously empty: '+file)
trace=(DOC/'REQUIREMENTS_TRACEABILITY.md').read_text(encoding='utf-8')
rows=re.findall(r'^\| (REQ-\d{3}) \| ([^|]+) \| ([^|]+) \| (APPROVED(?:-CONCEPT)?|OPEN|SUPERSEDED) \| \[([^\]]+)\]\(([^)]+)\) \| ([^|]+) \|$',trace,re.M)
ids=[r[0] for r in rows]
if len(ids)<205:errors.append(f'Expected at least 205 requirement rows, got {len(ids)}')
if len(ids)!=len(set(ids)):errors.append('Duplicate REQ IDs')
expected=[f'REQ-{i:03d}' for i in range(1,len(ids)+1)]
if ids!=expected:errors.append('REQ IDs missing or out of sequence')
for rid,src,desc,status,shown,rel,check in rows:
    p=(DOC/rel).resolve()
    if not p.is_file():errors.append(f'{rid}: target not found: {rel}')
    elif rid not in p.read_text(encoding='utf-8'):
        errors.append(f'{rid}: not cross-linked from target {rel}')
    if not src or not check:errors.append(f'{rid}: no provenance/check')

# Every referenced QA must exist. Every OPEN requirement must point to one exact
# OPEN ID, and every current OPEN question must have a trace row.
quality=(DOC/'QUALITY_AND_TEST_MATRIX.md').read_text(encoding='utf-8')
qa_ids=set(re.findall(r'^\| (QA-\d{3}) \|',quality,re.M))
for rid,src,desc,status,shown,rel,check in rows:
    for qa in re.findall(r'QA-\d{3}',check):
        if qa not in qa_ids:errors.append(f'{rid}: missing acceptance scenario {qa}')
    if status=='OPEN' and not re.fullmatch(r'OPEN-\d{3}',check.strip()):
        errors.append(f'{rid}: OPEN row must reference one OPEN ID, got {check.strip()}')
open_text=(DOC/'OPEN_QUESTIONS.md').read_text(encoding='utf-8')
open_ids=set(re.findall(r'^\| (OPEN-\d{3}) \|',open_text,re.M))
trace_open_ids={r[6].strip() for r in rows if r[3]=='OPEN'}
for oid in sorted(open_ids-trace_open_ids):errors.append(f'{oid}: no OPEN requirement row')
for oid in sorted(trace_open_ids-open_ids):errors.append(f'{oid}: trace references missing OPEN question')
expected_open={'OPEN-034','OPEN-035','OPEN-036','OPEN-037','OPEN-039','OPEN-040','OPEN-042','OPEN-018','OPEN-019','OPEN-020'}
if open_ids!=expected_open:errors.append(f'Current OPEN set differs: missing={sorted(expected_open-open_ids)}, extra={sorted(open_ids-expected_open)}')
for rid in ('REQ-131','REQ-188','REQ-189'):
    row=next((r for r in rows if r[0]==rid),None)
    if not row or row[3]!='APPROVED':errors.append(f'{rid} should be approved after 25.11.2026 decisions')
# Basic Markdown table integrity check.
for p in ROOT.rglob('*.md'):
    for lineno, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
        if line.lstrip().startswith('|') and not line.rstrip().endswith('|'):
            errors.append(f'Malformed Markdown table row: {p.relative_to(ROOT)}:{lineno}')
# Validate relative Markdown links (skip anchors, https, mailto, Windows paths).
for p in ROOT.rglob('*.md'):
    content=p.read_text(encoding='utf-8')
    for href in re.findall(r'(?<!!)\[[^\]]+\]\(([^\)]+)\)',content):
        dest=href.split('#')[0]
        if not dest or dest.startswith(('http://','https://','mailto:','C:','file://')):continue
        if dest.startswith('skills://'):continue
        if not (p.parent/dest).resolve().exists():errors.append(f'Broken link: {p.relative_to(ROOT)} -> {href}')
# Semantics: current normative contract must contain key user decisions.
keychecks={
 'docs/CURRENT_MVP_BASELINE.md':['единая точка входа','пользовательских редакций курса нет','не менее X правильных ответов из Y','Баллы существуют как награда','любому сотруднику компании','ровно три вкладки'],
 'docs/COURSES_EDITOR_UI.md':['Самостоятельной вкладки «Материалы» **нет**','перенести в другой раздел','К программе курса','Копировать из другого курса','вставить Google Docs','Сохранить черновик'],
 'docs/KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md':['одна кнопка','статья находится ровно в одной папке','Редакция принадлежит целой статье','MP4','MP3','текущие и будущие'],
 'docs/REVIEW_CENTER_NEXT.md':['**Ровно три вкладки.**','«Требует действий»','«Проверка отдельных материалов»','«Проверка курсов обучений»','**Не правый drawer.**','«Все действия»'],
 'docs/TEST_REVIEW_WORKFLOWS.md':['**A. «Исправить только свободный ответ»','**B. «Пройти тест заново»','атомарная','Просмотреть ответы и попытки'],
 'AGENTS.md':['**На production запрещено редактировать исходный код.**','**Никаких `commit`, `push`, tag, release без отдельного явного разрешения пользователя','origin/main','docs/CURRENT_MVP_BASELINE.md'],
 'docs/OPEN_QUESTIONS.md':['OPEN-042'],
 'docs/UI_NAVIGATION.md':['«Обучение»','«Курсы»','«Обновления»','«База знаний»','«Профиль»'],
 'docs/DATA_MODEL.md':['`articles`','`materials`','`knowledge_folders`','`knowledge_folder_articles`','`knowledge_access_grants`','`audio_assets`','`google_text_snapshots`'],
 'docs/CONTENT_REVISIONS.md':['Редакция фиксирует текст Tiptap','компактный текстовый снимок','«Полный тест»'],
}
for name,needles in keychecks.items():
    src=(ROOT/name).read_text(encoding='utf-8')
    for needle in needles:
        if needle.lower() not in src.lower():errors.append(f'Critical requirement text missing {name}: {needle}')
adr=(DOC/'DECISIONS.md').read_text(encoding='utf-8')
if len(re.findall(r'^\| ADR-\d{3} \| APPROVED',adr,re.M))<50:errors.append('Too few approved decisions')
if len(re.findall(r'^\| OLD-\d{3} \| SUPERSEDED',adr,re.M))<7:errors.append('Superseded decisions not tracked')
adr_ids=re.findall(r'^\| (ADR-\d{3}) \|',adr,re.M)
if len(adr_ids)!=len(set(adr_ids)):errors.append('Duplicate ADR IDs')

# Current contracts must not contain retired models. Historical files are
# intentionally excluded because they preserve SUPERSEDED decisions.
active_contracts=[
    'README.md','AGENTS.md','docs/CURRENT_MVP_BASELINE.md',
    'docs/ARCHITECTURE.md','docs/DATA_MODEL.md','docs/ERD.md',
    'docs/CONTENT_REVISIONS.md','docs/ACCESS_AND_ROLES.md',
    'docs/COURSES_EDITOR_UI.md','docs/KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md',
    'docs/COURSE_ASSIGNMENTS.md','docs/REVIEW_CENTER_NEXT.md',
    'docs/TEST_REVIEW_WORKFLOWS.md','docs/UI_NAVIGATION.md',
    'docs/MVP_CONTRACT.md','docs/OPEN_QUESTIONS.md',
    'docs/WORK_PLAN.md','docs/WORK_HANDOFF_PROMPT.md','docs/НАЧАТЬ-ЗДЕСЬ.md'
]
forbidden={
    'course_revision_id':'course revision FK',
    'course_revisions':'course revision entity',
    'material_revisions':'internal material revision entity',
    'test_revision_id':'test revision FK',
    'manual_points':'numeric free-answer score',
    'pass_points':'points-based pass threshold',
    'pass_percent':'percentage-based pass threshold',
    'опубликованная редакция курса':'published course revision',
    'новая редакция курса':'new course revision',
    'баллы по вопросам':'per-question points',
    'ручные баллы':'manual numeric points',
    'для своих назначений':'teacher limited to own assignments',
    'в пределах разрешённой области':'obsolete teacher scope wording',
    'pinned course revision':'pinned course revision wording',
    'опубликованную ревизию':'published course revision wording',
    'закреплёнными версиями':'frozen course campaign wording',
    'полноценная папочная база знаний документов и видео':'old deferred knowledge base',
    'в mvp отложенная база знаний':'old knowledge placeholder',
    'только google docs имеет датированные':'old revision owner',
    'google docs сохраняет датированные редакции':'old revision owner',
    'отдельное дерево/область документов':'old split knowledge base',
    'будущая загрузка файла с сервера':'old deferred upload',
    'мое обучение» (':'old user navigation',
    'в mvp страницы-заглушки':'old knowledge placeholder',
    'полноценная база знаний/видеотека после mvp':'old knowledge boundary',
    'курс хранит логический документ':'old course Google item',
}
closed_open_ids={
    'OPEN-001','OPEN-002','OPEN-004','OPEN-006','OPEN-007','OPEN-008',
    'OPEN-014','OPEN-015','OPEN-016','OPEN-017','OPEN-021',
    'OPEN-003','OPEN-012','OPEN-013','OPEN-025','OPEN-026','OPEN-027','OPEN-028','OPEN-029','OPEN-030',
    'OPEN-031','OPEN-032','OPEN-033','OPEN-038'
}
for name in active_contracts:
    src=(ROOT/name).read_text(encoding='utf-8').lower()
    for needle,label in forbidden.items():
        if needle.lower() in src:errors.append(f'Retired {label} remains in active contract {name}: {needle}')
    for oid in closed_open_ids:
        if oid in src:errors.append(f'Closed question {oid} remains in active contract {name}')

# The immutable uploaded original must stay byte-for-byte intact.
original_hash=hashlib.sha256((ROOT/'references/AGENTS.original.md').read_bytes()).hexdigest()
if original_hash!='c8c6e01b8725a79231b39ed2917dd23ccd4ba1f5ee5b9850656748f1bb1d0dd8':
    errors.append('references/AGENTS.original.md hash changed')

# Manifest covers every persistent file except itself.
manifest_path=ROOT/'MANIFEST.sha256'
manifest_entries={}
for line in manifest_path.read_text(encoding='utf-8').splitlines():
    match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
    if not match:
        errors.append(f'Malformed manifest row: {line}')
        continue
    digest,rel=match.groups()
    manifest_entries[rel]=digest
actual_files={
    p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
    if p.is_file() and p.name!='MANIFEST.sha256'
    and not p.relative_to(ROOT).as_posix().startswith(('.playwright-cli/','output/'))
    and p.relative_to(ROOT).as_posix()!='docs.zip'
}
for rel in sorted(actual_files-set(manifest_entries)):
    errors.append(f'Manifest missing file: {rel}')
for rel in sorted(set(manifest_entries)-actual_files):
    errors.append(f'Manifest references missing file: {rel}')
for rel in sorted(actual_files & set(manifest_entries)):
    digest=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
    if digest!=manifest_entries[rel]:errors.append(f'Manifest hash mismatch: {rel}')
# Archive check: optional if archive sibling exists.
archive=ROOT.parent/(ROOT.name+'.zip')
if archive.exists():
    try:
        with zipfile.ZipFile(archive) as z:
            bad=z.testzip()
            if bad: errors.append('Corrupt ZIP member '+bad)
            for path in REQUIRED:
                if f'{ROOT.name}/{path}' not in z.namelist():errors.append('Missing ZIP member: '+path)
    except Exception as ex:errors.append('Bad ZIP: '+repr(ex))
print(f'Required files: {len(REQUIRED)}; trace rows: {len(rows)}; approved ADRs: {len(re.findall(r"^\| ADR-\\d{{3}} \\| APPROVED",adr,re.M))}; errors: {len(errors)}')
if errors:
    for err in errors:print('FAIL:',err)
    sys.exit(1)
print('PASS: files and manifest, sequential REQ links, QA references, OPEN/REQ sync, Markdown links, current semantic invariants, superseded history, original AGENTS hash, archive integrity (if present).')
print('SCOPE: this validates specification readiness and known stale-rule guards; runtime behavior still requires implementation tests.')


