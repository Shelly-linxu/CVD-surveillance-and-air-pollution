"""Resumable Tencent supplement: address-only signed HTTPS; free quota only."""
import json,sqlite3,time,os,fcntl,csv,subprocess,html
from urllib.request import Request,urlopen
import baidu_geocoding as b
from tencent_geocoding_pilot import signed_url,select
P=b.P;O=b.O;CAP=5900

def sync_queue(c):
    src=sqlite3.connect('file:'+str(P/'baidu_geocoding.sqlite')+'?mode=ro',uri=True)
    for row in src.execute('select id,address,ids from queries where stage="unresolved"'):
        c.execute('insert or ignore into queries(id,address,ids) values(?,?,?)',row)
    remaining=src.execute('select count(*) from queries where stage in ("pending","temporary_error")').fetchone()[0]
    src.close();c.commit();return remaining

def used_today(c):
    return c.execute('select count(*) from ledger where substr(created,1,10)=?',(b.now().date().isoformat(),)).fetchone()[0]

def export(c,state):
    rows=[]
    for qid,ids,s in c.execute('select id,ids,selection from queries where stage="selected"'):
        g=json.loads(s);x,y=map(float,g.pop('location').split(','));g.pop('formatted_address',None)
        rows.append(dict(local_query_id=qid,local_location_ids=ids,gcj02_longitude=x,gcj02_latitude=y,longitude='',latitude='',crs='EPSG:4326',**g))
    if rows:
        run=subprocess.run(['node',str(b.ROOT/'work/air_pollution_cc/convert_full_coordinates.cjs')],input=json.dumps(rows),text=True,capture_output=True,check=True);rows=json.loads(run.stdout)
    fpath=P/'tencent_selected_coordinates.csv';tmp=fpath.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        fields=list(rows[0]) if rows else ['local_query_id','local_location_ids','longitude','latitude']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    os.chmod(tmp,0o600);tmp.replace(fpath)
    counts=dict(c.execute('select stage,count(*) from queries group by stage'))
    s={'updated_at':b.now().isoformat(),'process_id':os.getpid(),'state':state,'query_counts':counts,'today_requests':used_today(c),'requests_including_pilot':c.execute('select count(*) from ledger').fetchone()[0],'last_request':c.execute('select max(created) from ledger').fetchone()[0],'daily_hard_cap':CAP,'provider_daily_free_quota_observed':6000,'key_qps_allocation':3,'selected_original_addresses':sum(len(r['local_location_ids'].split('|')) for r in rows),'verified_within_1km':0,'free_only':True,'queue_policy':'Baidu unresolved addresses; existing 100 pilot rows retained; refill from Baidu at each check'}
    (O/'tencent_geocoding_status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
    (O/'腾讯补充地址匹配进度.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="60"><title>腾讯补充地址匹配进度</title><style>body{font:17px sans-serif;max-width:950px;margin:40px auto;line-height:1.8}pre{background:#eef3f8;padding:20px;white-space:pre-wrap}</style><h1>腾讯补充地址匹配进度</h1><p>优先处理百度已经尝试但仍无可靠坐标的住址。仅发送住址文字；每天最多5900次，含测试及重试，不购买服务。队列暂时处理完后等待百度产生更多未定位地址，由30分钟检查继续衔接。</p><p>通过地址一致性筛选的候选坐标仍需独立核验实际精度，不能直接视为满足1km要求。</p><pre>'+html.escape(json.dumps(s,ensure_ascii=False,indent=2))+'</pre>')
    print(json.dumps(s,ensure_ascii=False),flush=True)

def main():
    if __import__('os').environ.get('GEOCODING_AUTHORIZED') != 'YES':
        raise RuntimeError('External address geocoding is disabled. Obtain data-custodian approval before setting GEOCODING_AUTHORIZED=YES.')
    fd=os.open(P/'tencent_geocoding.lock',os.O_CREAT|os.O_WRONLY,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Tencent worker already holds lock')
    c=sqlite3.connect(P/'tencent_geocoding.sqlite');c.execute('pragma journal_mode=WAL');c.execute('pragma synchronous=FULL')
    c.executescript('create table if not exists queries(id text primary key,address text,ids text,stage text default "pending",reason text,response text,selection text);create table if not exists ledger(id integer primary key,created text);');os.chmod(P/'tencent_geocoding.sqlite',0o600)
    sync_queue(c);key=json.loads((P/'tencent_key.json').read_text());state='running';export(c,state)
    try:
        while state=='running':
            row=c.execute('select id,address from queries where stage in ("pending","temporary_error") order by id limit 1').fetchone()
            if row is None:
                remaining=sync_queue(c)
                row=c.execute('select id,address from queries where stage in ("pending","temporary_error") order by id limit 1').fetchone()
                if row is None:state='waiting_upstream' if remaining else 'finished';break
            qid,address=row;variant=b.amap.building(b.amap.norm(address));r=None
            for attempt in range(3):
                if used_today(c)>=CAP:state='waiting_daily_quota_reset';break
                c.execute('insert into ledger(created) values(?)',(b.now().isoformat(),));c.commit()
                try:
                    with urlopen(Request(signed_url(variant,key),headers={'x-legacy-url-decode':'no'}),timeout=40) as f:r=json.load(f)
                except Exception:r={'status':-1,'message':'network_error'}
                time.sleep(.6)
                code=r.get('status')
                if code in (0,310,311):break
                if code in (-1,120,199):time.sleep(2*(attempt+1));continue
                state='waiting_daily_quota_reset' if code==121 else 'stopped_provider_status_'+str(code);break
            if state!='running':break
            sel,reason=select(variant,r);stage='selected' if sel else 'unresolved'
            if r.get('status') in (-1,120,199):stage='temporary_error';state='stopped_transient_failure'
            c.execute('update queries set stage=?,reason=?,response=?,selection=? where id=?',(stage,reason,json.dumps(r,ensure_ascii=False),json.dumps(sel,ensure_ascii=False) if sel else None,qid));c.commit()
            if used_today(c)%100==0:export(c,state)
    except Exception:
        export(c,'stopped_local_error');raise
    export(c,state)
if __name__=='__main__':main()
