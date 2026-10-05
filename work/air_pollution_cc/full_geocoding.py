"""Full address-only AMap matching with resumable local SQLite state and hard free quotas.
No patient identifiers or diagnoses enter HTTP parameters. Candidate ambiguity is retained.
"""
import csv,json,os,re,sqlite3,time,unicodedata,hashlib,threading,subprocess,html
from pathlib import Path
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen
from urllib.parse import urlencode
from collections import Counter
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'work/air_pollution_cc/private';O=ROOT/'outputs/air_pollution_cc'
DB=P/'full_geocoding.sqlite';DISTRICTS={'荔湾区':'440103','越秀区':'440104','海珠区':'440105','天河区':'440106','白云区':'440111','黄埔区':'440112','番禺区':'440113','花都区':'440114','南沙区':'440115','从化区':'440117','增城区':'440118'}
BASIC_CAP=149750;SEARCH_CAP=4900 # conservative ceilings; includes the 103 previous requests

def norm(s):
    s=unicodedata.normalize('NFKC',s);s=re.sub(r'[\s，,；;。]+','',s)
    # Consecutive administrative repetitions only; retain all house/building numbers.
    for x in ['广东省','广州市',*DISTRICTS]:
        s=s.replace(x+x,x)
    return s

def district(s):return next((d for d in DISTRICTS if d in s),'')
def anchors(s):
    s=re.sub('广东省|广州市|'+'|'.join(DISTRICTS),'',s)
    s=re.sub(r'[\u4e00-\u9fff]{2,8}(?:街道|镇)','',s,count=1)
    road=re.findall(r'[\u4e00-\u9fff]{2,12}(?:大道|路|巷|街)(?!道)',s)
    nums=re.findall(r'(\d+(?:-\d+)?)(?:号|栋|幢|座)',s)
    return road,nums

def building(s):
    # Preserve the final identified building. Strip only explicit room/unit/floor suffix.
    m=re.search(r'(\d+(?:号|栋|幢|座|楼))((?:\d+单元)?(?:\d+[层楼])?(?:\d+(?:室|房))?)$',s)
    if m and m.group(2):return s[:m.end(1)]
    return s

def fallback(s):
    # Broader anchor is marked coarse, never a restored exact house coordinate.
    cut=re.search(r'\d+(?:号|栋|幢|座)',s)
    if cut:return s[:cut.end()]
    cut=re.search(r'(?:社区|小区|花园|大厦|村)(?!委)',s)
    if cut:return s[:cut.end()]
    return ''

def score(s,g):
    formatted=norm(str(g.get('formatted_address','')));d=district(s)
    if d and d not in formatted:return -1,'district_conflict'
    if not str(g.get('adcode','')).startswith('4401'):return -1,'outside_guangzhou'
    road,nums=anchors(s);targetroad,targetnums=anchors(formatted)
    if road and not any(r in formatted for r in road):return -1,'road_conflict_or_missing'
    if nums and targetnums and nums[0]!=targetnums[0]:return -1,'house_number_conflict'
    # Text similarity is secondary to explicit administrative and numeric anchors.
    a=re.sub('广东省|广州市|'+'|'.join(DISTRICTS),'',s)
    b=re.sub('广东省|广州市|'+'|'.join(DISTRICTS),'',formatted)
    sim=SequenceMatcher(None,a,b).ratio()
    strong=bool(road and nums and nums[0] in targetnums)
    return min(1,sim+(.18 if strong else 0)), 'road_and_number_agree' if strong else 'text_and_district'

def choose(s,result,method='direct'):
    candidates=result.get('geocodes',[]);rank=[]
    for g in candidates:
        try:
            xy=[float(x) for x in g.get('location','').split(',')]
            if len(xy)!=2 or not (-180<=xy[0]<=180 and -90<=xy[1]<=90):continue
        except (ValueError,TypeError):continue
        val,reason=score(s,g);rank.append((val,reason,g))
    rank.sort(key=lambda x:x[0],reverse=True)
    if not rank:return None,'unmatched'
    val,reason,g=rank[0];margin=val-(rank[1][0] if len(rank)>1 else -1)
    if val<0:return None,'candidate_conflict'
    if len(rank)>1 and (val<.72 or margin<.15):return None,'ambiguous'
    if len(rank)==1 and val<.35:return None,'weak_text_match'
    # A provider level alone never certifies actual spatial accuracy.
    quality='door_or_building_unverified' if g.get('level') in ('门牌号','门址') and reason=='road_and_number_agree' and method=='direct' else 'coarse_or_fuzzy_unverified'
    return dict(g,match_score=round(val,4),candidate_margin=round(margin,4),match_method=method,match_quality=quality,verified_within_1km=0), 'selected'

def connect():
    c=sqlite3.connect(DB);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA synchronous=FULL')
    c.executescript('''CREATE TABLE IF NOT EXISTS queries(id TEXT PRIMARY KEY,address TEXT,stage TEXT DEFAULT 'pending',selection TEXT,reason TEXT,attempts INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS links(query_id TEXT PRIMARY KEY,canonical_id TEXT);
    CREATE TABLE IF NOT EXISTS responses(address TEXT PRIMARY KEY,result TEXT);
    CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY,service TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY,value TEXT);''');c.commit();os.chmod(DB,0o600);return c

def prepare(c):
    if c.execute('SELECT count(*) FROM links').fetchone()[0]:return
    rows=list(csv.DictReader((P/'geocoding_normalized_queries_v2.csv').open(encoding='utf-8-sig')))
    for row in rows:
        address=building(norm(row['address']));cid=hashlib.sha256(address.encode()).hexdigest()[:24]
        c.execute('INSERT OR IGNORE INTO queries(id,address) VALUES(?,?)',(cid,address))
        c.execute('INSERT INTO links VALUES(?,?)',(row['location_id'],cid))
    # Import known pilot responses with exact original request association.
    old={r['location_id']:r['address'] for r in csv.DictReader((P/'geocoding_test_100.csv').open(encoding='utf-8-sig'))}
    restored={r['location_id']:r['address'] for r in csv.DictReader((P/'geocoding_test_restore_3.csv').open(encoding='utf-8-sig'))}
    for fn,mapping in [('amap_geocoding_results.jsonl',old),('amap_geocoding_corrections.jsonl',restored)]:
        for line in (P/fn).read_text().splitlines():
            r=json.loads(line);address=norm(mapping[r['location_id']]);c.execute('INSERT OR REPLACE INTO responses VALUES(?,?)',(address,json.dumps(r,ensure_ascii=False)))
    c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('authorization','用户授权全量地址及模糊匹配；仅发送地址文字至高德，不发送姓名、身份证或疾病，不购买付费服务'))
    c.commit()

class QuotaStop(Exception):pass
class ProviderStop(Exception):pass
RETRYABLE_CODES={'10004','10015','10016','10019','10020','10021','10029','NETWORK_ERROR','30001','30002','30003'}
ENGINE_CODES={'30001','30002','30003'}
def check_response(result):
    code=str(result.get('infocode','UNKNOWN'))
    if result.get('status')!='1' and code not in RETRYABLE_CODES:
        stop_event.set();raise ProviderStop(code)
lock=threading.Lock();next_request=0.;request_interval=.50;stop_event=threading.Event()
def request(key,s,service):
    global next_request,request_interval
    if stop_event.is_set():raise ProviderStop()
    with lock:
        c=sqlite3.connect(DB);total=c.execute('SELECT count(*) FROM ledger WHERE service=?',(service,)).fetchone()[0]+(103 if service=='basic' else 0)
        if total>=(BASIC_CAP if service=='basic' else SEARCH_CAP):c.close();raise QuotaStop()
        delay=next_request-time.monotonic()
        if delay>0:time.sleep(delay)
        next_request=time.monotonic()+request_interval # conservative pacing, including retries
        c.execute('INSERT INTO ledger(service,created) VALUES(?,?)',(service,time.strftime('%Y-%m-%dT%H:%M:%S%z')));c.commit();c.close()
    params={'key':key,'output':'JSON'}
    if service=='basic':params.update(address=s,city='广州市');path='geocode/geo'
    else:
        d=district(s);keyword=re.sub('广东省|广州市|'+'|'.join(DISTRICTS),'',s)
        params.update(keywords=keyword,city=DISTRICTS.get(d,'440100'),citylimit='true',offset=10,page=1,extensions='base');path='place/text'
    try:
        with urlopen('https://restapi.amap.com/v3/'+path+'?'+urlencode(params),timeout=25) as r:result=json.load(r)
    except Exception:return {'status':'0','infocode':'NETWORK_ERROR'}
    check_response(result)
    if result.get('infocode') in ('10015','10019','10020','10021','10029'):
        with lock:request_interval=min(2.,max(.75,request_interval*1.5));next_request=time.monotonic()+5.
    if service=='search':
        result['geocodes']=[dict(formatted_address=str(g.get('pname',''))+str(g.get('cityname',''))+str(g.get('adname',''))+str(g.get('address',''))+str(g.get('name','')),adcode=g.get('adcode',''),location=g.get('location',''),level='兴趣点',poi_id=g.get('id','')) for g in result.get('pois',[])]
    return result

def task(key,row,cache,service='basic'):
    qid,address=row;variant=address if service=='basic' else fallback(address)
    if not variant:return qid,None,'no_safe_fallback',None,None
    result=cache.get(('search:' if service=='search' else '')+variant)
    if result is None:
        for attempt in range(3):
            try:result=request(key,variant,service)
            except QuotaStop:return qid,None,'free_quota_exhausted',None,None
            if result.get('status')=='1':break
            time.sleep(2*(attempt+1))
    if result.get('status')!='1':
        reason='provider_engine_error_'+str(result.get('infocode')) if str(result.get('infocode')) in ENGINE_CODES else 'temporary_network_or_rate_error'
        return qid,None,reason,variant,result
    selected,reason=choose(address,result,'direct' if service=='basic' else 'district_constrained_fuzzy_search')
    return qid,selected,reason,variant,result

def export(c,state):
    counts=dict(c.execute('SELECT stage,count(*) FROM queries GROUP BY stage'));qtotal=c.execute('SELECT count(*) FROM queries').fetchone()[0]
    links=c.execute('SELECT count(*) FROM links').fetchone()[0];basic=103+c.execute("SELECT count(*) FROM ledger WHERE service='basic'").fetchone()[0];search=c.execute("SELECT count(*) FROM ledger WHERE service='search'").fetchone()[0]
    raw=[];byid={};qualities=Counter()
    for qid,stage,sel,reason in c.execute('SELECT id,stage,selection,reason FROM queries'):
        p=json.loads(sel) if sel else {};xy=p.get('location','').split(',')
        row=dict(canonical_id=qid,status=stage,reason=reason or '',match_method=p.get('match_method',''),match_quality=p.get('match_quality',''),provider_level=p.get('level',''),adcode=p.get('adcode',''),match_score=p.get('match_score',''),candidate_margin=p.get('candidate_margin',''),gcj02_longitude=float(xy[0]) if len(xy)==2 else '',gcj02_latitude=float(xy[1]) if len(xy)==2 else '',longitude='',latitude='',crs='EPSG:4326',verified_within_1km=0)
        byid[qid]=row
        if p:raw.append(row);qualities[row['match_quality']]+=1
    if raw:
        run=subprocess.run(['node',str(ROOT/'work/air_pollution_cc/convert_full_coordinates.cjs')],input=json.dumps(raw),text=True,capture_output=True,check=True)
        for p in json.loads(run.stdout):byid[p['canonical_id']]=p
    mapped={qid:byid[cid] for qid,cid in c.execute('SELECT query_id,canonical_id FROM links')};path=P/'all_address_matching.csv';tmp=path.with_suffix('.tmp');resolved=0
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        fields=['location_id','query_id',*list(next(iter(byid.values())))]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for link in csv.DictReader((P/'geocoding_normalized_map_v2.csv').open(encoding='utf-8-sig')):
            # Original map schemas are checked during preparation below.
            qid=link['query_id'];loc=link['location_id'];p=mapped[qid];w.writerow(dict(location_id=loc,query_id=qid,**p));resolved+=p['status'] in ('selected','approximate')
    os.chmod(tmp,0o600);tmp.replace(path)
    summary=dict(updated_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),process_id=os.getpid(),state=state,original_addresses=152764,normalized_queries=links,canonical_building_queries=qtotal,query_counts=counts,original_addresses_with_selected_coordinates=resolved,canonical_selected_by_quality=dict(qualities),basic_requests_including_pilot=basic,basic_hard_cap=BASIC_CAP,search_requests=search,search_hard_cap=SEARCH_CAP,certified_within_1km=0,association_models_fitted=0,privacy='仅地址文字发送至高德；密钥、住址及坐标在本地私有目录',note='坐标覆盖与1 km定位准确性不同；模糊、粗定位和未核验结果不能直接充当主分析高精度地址。')
    writejson(O/'full_geocoding_status.json',summary)
    body=html.escape(json.dumps(summary,ensure_ascii=False,indent=2));report=f'<!doctype html><meta charset="utf-8"><title>全量地址匹配进度</title><style>body{{font:17px sans-serif;max-width:1000px;margin:40px auto;line-height:1.7}}pre{{white-space:pre-wrap;background:#f3f5f7;padding:20px}}</style><h1>全量地址匹配进度</h1><p>标准查询 → 行政区、道路和门牌核查 → 限定行政区模糊搜索。粗定位、冲突及无法消除的多候选均保留质量标签。此报告仅含汇总，不含住址、患者标识、坐标或密钥。</p><pre>{body}</pre><p>私有结果：work/air_pollution_cc/private/all_address_matching.csv。运行中每500条查询更新结果及报告；浏览器刷新即可查看最新存档。</p>'
    import render_geocoding_progress
    (O/'全量地址匹配进度.html').write_text(render_geocoding_progress.render(summary))
    print(json.dumps(summary,ensure_ascii=False),flush=True)

def writejson(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.replace(path)

def main():
    if __import__('os').environ.get('GEOCODING_AUTHORIZED') != 'YES':
        raise RuntimeError('External address geocoding is disabled. Obtain data-custodian approval before setting GEOCODING_AUTHORIZED=YES.')
    import argparse,fcntl
    ap=argparse.ArgumentParser();ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--max-primary',type=int,default=0);args=ap.parse_args()
    lockfd=os.open(P/'full_geocoding.lock',os.O_CREAT|os.O_WRONLY,0o600)
    try:fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Another matching process holds the lock.')
    c=connect();prepare(c)
    # Validate all original address IDs are represented once before external requests.
    original=list(csv.DictReader((P/'geocoding_normalized_map_v2.csv').open(encoding='utf-8-sig')))
    assert len(original)>0 and len({r['location_id'] for r in original})==len(original)
    export(c,'prepared' if args.prepare_only else 'running_standard_matching')
    if args.prepare_only:return
    key=json.loads((P/'amap_key.json').read_text())['amap_web_key'];state='finished';processed=0
    for qid,address,result in c.execute("SELECT q.id,q.address,r.result FROM queries q JOIN responses r ON q.address=r.address WHERE q.stage='pending'").fetchall():
        selected,reason=choose(address,json.loads(result))
        c.execute('UPDATE queries SET stage=?,selection=?,reason=? WHERE id=?',('selected' if selected else 'needs_fuzzy',json.dumps(selected,ensure_ascii=False) if selected else None,reason,qid))
    c.commit();export(c,'running_standard_matching')
    try:
        for service in ('basic','search'):
            cache={a:json.loads(r) for a,r in c.execute('SELECT address,result FROM responses')}
            if service=='basic':rows=c.execute("SELECT id,address FROM queries WHERE stage IN ('pending','temporary_error') ORDER BY id").fetchall()
            else:
                stages="('needs_fuzzy','pending')" if state=='stopped_at_free_quota' else "('needs_fuzzy')"
                rows=c.execute(f"SELECT id,address FROM queries WHERE stage IN {stages} ORDER BY CASE WHEN stage='pending' THEN 0 ELSE 1 END,attempts,id").fetchall()
                if args.max_primary:rows=rows[:20]
            if args.max_primary and service=='basic':rows=rows[:args.max_primary]
            with ThreadPoolExecutor(max_workers=1) as pool:
                # Bound submitted work and avoid holding 150k futures in memory.
                for start in range(0,len(rows),30):
                    batch=[]
                    for item in pool.map(lambda row:task(key,row,cache,service),rows[start:start+30]):
                        batch.append(item)
                        qid,selected,reason,address,result=item
                        if result and result.get('status')=='1':
                            cachekey=('search:' if service=='search' else '')+address
                            cache[cachekey]=result;c.execute('INSERT OR REPLACE INTO responses VALUES(?,?)',(cachekey,json.dumps(result,ensure_ascii=False)))
                        stage='selected' if selected else ('temporary_error' if reason=='temporary_network_or_rate_error' else ('pending' if reason=='free_quota_exhausted' else ('needs_fuzzy' if service=='basic' else 'unresolved')))
                        c.execute('UPDATE queries SET stage=?,selection=?,reason=?,attempts=attempts+1 WHERE id=?',(stage,json.dumps(selected,ensure_ascii=False) if selected else None,reason,qid))
                        # Preserve each completed address even if a later request stops the batch.
                        c.commit()
                    c.commit();processed+=len(batch)
                    if sum(x[2]=='temporary_network_or_rate_error' or x[2].startswith('provider_engine_error_') for x in batch)>=10:
                        state='stopped_repeated_service_errors';stop_event.set();break
                    if any(x[2]=='free_quota_exhausted' for x in batch):
                        state='stopped_at_free_quota';break
                    if start%510==0:export(c,'running_standard_matching' if service=='basic' else 'running_fuzzy_matching')
            export(c,'standard_pass_finished' if service=='basic' else 'fuzzy_pass_finished')
            if stop_event.is_set():break
        if state=='finished' and c.execute("SELECT count(*) FROM queries WHERE stage='pending'").fetchone()[0]:state='partial_run_limit'
    except QuotaStop:state='stopped_at_free_quota'
    except ProviderStop as exc:state='stopped_provider_error_'+str(exc)
    except Exception:
        export(c,'stopped_local_error');raise
    if not args.max_primary and not stop_event.is_set():
        import local_address_fallback,sys
        print(json.dumps(local_address_fallback.apply(c,sys.modules[__name__]),ensure_ascii=False),flush=True)
    export(c,state)
if __name__=='__main__':main()
