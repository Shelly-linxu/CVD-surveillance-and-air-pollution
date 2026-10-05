"""Authorized 100-address Tencent pilot. Private cache; address-only HTTPS requests."""
import json,sqlite3,hashlib,time,os,fcntl,csv,subprocess
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import baidu_geocoding as b
import full_geocoding as a
P=b.P;O=b.O;LIMIT=100

def signed_url(address,key):
    params={'address':address,'key':key['key'],'output':'json','policy':'0','region':'广州市'}
    raw='&'.join(f'{k}={params[k]}' for k in sorted(params))
    sig=hashlib.md5(('/ws/geocoder/v1/?'+raw+key['sk']).encode()).hexdigest()
    return 'https://apis.map.qq.com/ws/geocoder/v1/?'+urlencode(params)+'&sig='+sig

def select(address,res):
    if res.get('status')!=0:return None,'provider_error'
    r=res.get('result',{});ac=r.get('address_components',{});xy=r.get('location',{});ad=str(r.get('ad_info',{}).get('adcode',''))
    try:x=float(xy['lng']);y=float(xy['lat'])
    except (KeyError,TypeError,ValueError):return None,'missing_coordinate'
    if not ad.startswith('4401') or not (112.5<x<114.7 and 22<y<24.8):return None,'outside_guangzhou'
    if a.district(address) and a.district(address)!=ac.get('district'):return None,'district_conflict'
    formatted=''.join(str(ac.get(k,'')) for k in ['province','city','district','street','street_number'])+str(r.get('title',''))
    g={'formatted_address':formatted,'location':f'{x},{y}','adcode':ad}
    score,why=a.score(address,g)
    road,nums=a.anchors(address);tr,tn=a.anchors(a.norm(formatted))
    if score<.55 or (nums and (not tn or nums[0]!=tn[0])):return None,'candidate_conflict_or_insufficient_anchor'
    if float(r.get('reliability',0) or 0)<7:return None,'low_provider_reliability'
    return dict(g,match_score=score,level=r.get('level'),reliability=r.get('reliability'),similarity=r.get('similarity'),deviation=r.get('deviation'),match_quality='tencent_door_unverified' if r.get('level')==9 and why=='road_and_number_agree' else 'tencent_coarse_unverified',verified_within_1km=0),'selected'

def export(c,state):
    counts=dict(c.execute('select stage,count(*) from queries group by stage'))
    codes=dict(c.execute("select json_extract(response,'$.status'),count(*) from queries where response is not null group by 1"))
    out={'updated_at':b.now().isoformat(),'state':state,'pilot_target':LIMIT,'query_counts':counts,'provider_status_counts':codes,'requests':c.execute('select count(*) from ledger').fetchone()[0],'daily_free_quota_observed':6000,'key_daily_allocation':5900,'free_only':True,'verified_within_1km':0,'sampling':'100 previously unlocated addresses from untouched queue tail; not a random sample'}
    (O/'tencent_geocoding_pilot_status.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps(out,ensure_ascii=False),flush=True)
    rows=[]
    for qid,ids,s in c.execute("select id,ids,selection from queries where stage='selected'"):
        g=json.loads(s);x,y=map(float,g.pop('location').split(','));g.pop('formatted_address',None)
        rows.append(dict(local_query_id=qid,local_location_ids=ids,gcj02_longitude=x,gcj02_latitude=y,longitude='',latitude='',crs='EPSG:4326',**g))
    if rows:
        run=subprocess.run(['node',str(b.ROOT/'work/air_pollution_cc/convert_full_coordinates.cjs')],input=json.dumps(rows),text=True,capture_output=True,check=True)
        rows=json.loads(run.stdout)
        with (P/'tencent_pilot_selected_coordinates.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        os.chmod(P/'tencent_pilot_selected_coordinates.csv',0o600)

def main():
    if __import__('os').environ.get('GEOCODING_AUTHORIZED') != 'YES':
        raise RuntimeError('External address geocoding is disabled. Obtain data-custodian approval before setting GEOCODING_AUTHORIZED=YES.')
    fd=os.open(P/'tencent_geocoding.lock',os.O_CREAT|os.O_WRONLY,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    c=sqlite3.connect(P/'tencent_geocoding.sqlite');c.execute('pragma journal_mode=WAL')
    c.executescript('create table if not exists queries(id text primary key,address text,ids text,stage text default "pending",reason text,response text,selection text);create table if not exists ledger(id integer primary key,created text);')
    os.chmod(P/'tencent_geocoding.sqlite',0o600)
    if not c.execute('select count(*) from queries').fetchone()[0]:
        src=sqlite3.connect('file:'+str(P/'baidu_geocoding.sqlite')+'?mode=ro',uri=True)
        for row in src.execute('select id,address,ids from queries where stage="pending" order by id desc limit 100'):c.execute('insert into queries(id,address,ids) values(?,?,?)',row)
        src.close();c.commit()
    key=json.loads((P/'tencent_key.json').read_text());state='running';export(c,state)
    for qid,address in c.execute('select id,address from queries where stage="pending" order by id desc').fetchall():
        if c.execute('select count(*) from ledger').fetchone()[0]>=LIMIT+3:state='pilot_request_limit';break
        variant=a.building(a.norm(address));c.execute('insert into ledger(created) values(?)',(b.now().isoformat(),));c.commit()
        try:
            with urlopen(Request(signed_url(variant,key),headers={'x-legacy-url-decode':'no'}),timeout=40) as f:r=json.load(f)
        except Exception:r={'status':-1,'message':'network_error'}
        sel,reason=select(variant,r);stage='selected' if sel else 'unresolved'
        c.execute('update queries set stage=?,reason=?,response=?,selection=? where id=?',(stage,reason,json.dumps(r,ensure_ascii=False),json.dumps(sel,ensure_ascii=False) if sel else None,qid));c.commit()
        if r.get('status') not in (0,310,311):state='stopped_provider_status_'+str(r.get('status'));break
        if c.execute('select count(*) from ledger').fetchone()[0]%20==0:export(c,state)
        time.sleep(.6)
    if state=='running':state='pilot_finished'
    export(c,state)
if __name__=='__main__':main()
