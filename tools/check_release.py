"""Source-only publication check, confined to the clean export directory."""
from pathlib import Path
import ast,json,re,sys
R=Path(__file__).resolve().parents[1]
allowed_suffix={'.py','.R','.cjs','.md'}
allowed_names={'.gitignore','requirements.txt','package.json','package-lock.json','sources.example.json','model_parameters.example.json'}
errors=[];files=[]
patterns=[r'gh[pousr]_[A-Za-z0-9]{20,}',r'github_pat_[A-Za-z0-9_]{20,}',r'AKIA[0-9A-Z]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'(?<!\d)\d{17}[\dX](?!\d)',r'/Users/[A-Za-z0-9_.-]+/']
for p in sorted(R.rglob('*')):
 if not p.is_file() or any(part in ['.git','__pycache__','.venv','node_modules'] for part in p.relative_to(R).parts):continue
 rel=p.relative_to(R)
 if p.suffix not in allowed_suffix and p.name not in allowed_names:errors.append(f'Non-source artifact: {rel}');continue
 if any(part in ['private','outputs','data','原始数据'] for part in rel.parts):errors.append(f'Banned directory: {rel}')
 t=p.read_text(encoding='utf-8');files.append(str(rel))
 if p.suffix=='.py':
  try:ast.parse(t,filename=str(rel))
  except SyntaxError as e:errors.append(f'Python syntax: {rel}:{e.lineno}')
 for pattern in patterns:
  if re.search(pattern,t):errors.append(f'Possible secret/identity/home-path literal: {rel}');break
 if p.suffix=='.json':
  try:json.loads(t)
  except ValueError:errors.append(f'Invalid JSON: {rel}')
 if p.name.startswith(('build_manuscript','build_revision','revise_docs')):errors.append(f'Article builder: {rel}')
if errors:
 for e in errors:print(e)
 sys.exit(1)
print(f'PASS: {len(files)} allowed source/documentation files; Python and JSON parse; no detected secrets, identity literals, home paths or data artifacts.')
