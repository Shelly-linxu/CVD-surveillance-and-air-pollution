"""Address-only Baidu geocoding, signed HTTPS, private resumable cache and free daily cap."""
import csv,json,sqlite3,os,time,hashlib,fcntl,argparse,subprocess,html
from pathlib import Path
from urllib.parse import urlencode,quote_plus
from urllib.request import urlopen
from datetime import datetime
from zoneinfo import ZoneInfo
import full_geocoding as amap
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'work/air_pollution_cc/private';O=ROOT/'outputs/air_pollution_cc';CAP=4900

def now():return datetime.now(ZoneInfo('Asia/Shanghai'))
def signed_url(address,key):
 params={'address':address,'city':'广州市','output':'json','ak':key['ak'],'ret_coordtype':'gcj02ll','extension_analys_level':'true','extension_poi_infos':'true'}
 query=urlencode(params);sn=hashlib.md5(quote_plus('/geocoding/v3/?'+query+key['sk']).encode()).hexdigest()
 return 'https://api.map.baidu.com/geocoding/v3/?'+query+'&sn='+sn

def select(address,res):
 if res.get('status')!=0:return None,'provider_error'
 result=res.get('result',{});pois=res.get('poi_infos',[])
 if isinstance(pois,dict):pois=[pois]
 if not pois:return None,'no_structured_candidate_for_verification'
 ranked=[]
 for g in pois:
  xy=g.get('location',{});ad=str(g.get('adcode',''));formatted=str(g.get('formatted_address',''))+str(g.get('name',''))
  try:lng=float(xy['lng']);lat=float(xy['lat'])
  except (ValueError,KeyError,TypeError):continue
  if not ad.startswith('4401') or not (112.5<lng<114.7 and 22<lat<24.8):continue
  d=amap.district(address)
  if d and str(g.get('district',''))!=d:continue
  candidate={'formatted_address':formatted,'adcode':ad,'location':f'{lng},{lat}','level':g.get('level',result.get('level',''))}
  s,why=amap.score(address,candidate)
  if s<.55:continue
  road,nums=amap.anchors(address);tr,tn=amap.anchors(amap.norm(formatted))
  if nums and (not tn or nums[0]!=tn[0]):continue
  candidate.update(match_score=s,confidence=g.get('confidence',result.get('confidence')),comprehension=g.get('comprehension',result.get('comprehension')),precise=g.get('precise',result.get('precise')),analys_level=g.get('analys_level',result.get('analys_level')),match_method='baidu_signed_geocoding',verified_within_1km=0,match_quality='baidu_door_unverified' if candidate['level']=='门址' and why=='road_and_number_agree' else 'baidu_coarse_unverified')
  ranked.append(candidate)
 ranked.sort(key=lambda g:g['match_score'],reverse=True)
 if not ranked:return None,'candidate_conflict_or_insufficient_anchor'
 if len(ranked)>1 and ranked[0]['match_score']-ranked[1]['match_score']<.15 and ranked[0]['location']!=ranked[1]['location']:return None,'ambiguous'
 return ranked[0],'selected'

def export(c,state):
 rows=[]
 for qid,ids,sel in c.execute("select id,ids,selection from queries where stage='selected'"):
  g=json.loads(sel);x,y=map(float,g['location'].split(','));rows.append(dict(local_query_id=qid,local_location_ids=ids,gcj02_longitude=x,gcj02_latitude=y,longitude='',latitude='',crs='EPSG:4326',**{k:g.get(k,'') for k in ['adcode','level','confidence','comprehension','precise','analys_level','match_score','match_method','match_quality','verified_within_1km']}))
 if rows:
  run=subprocess.run(['node',str(ROOT/'work/air_pollution_cc/convert_full_coordinates.cjs')],input=json.dumps(rows),text=True,capture_output=True,check=True);rows=json.loads(run.stdout)
 fpath=P/'baidu_selected_coordinates.csv';tmp=fpath.with_suffix('.tmp')
 with tmp.open('w',encoding='utf-8-sig',newline='') as f:
  fields=list(rows[0]) if rows else ['local_query_id','local_location_ids','longitude','latitude'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 os.chmod(tmp,0o600);tmp.replace(fpath)
 counts=dict(c.execute('select stage,count(*) from queries group by stage'));used=c.execute('select count(*) from ledger where day=?',(now().date().isoformat(),)).fetchone()[0]
 s={'updated_at':now().isoformat(),'process_id':os.getpid(),'state':state,'target_original_addresses':37756,'query_counts':counts,'selected_original_addresses':sum(len(r['local_location_ids'].split('|')) for r in rows),'today_requests':used,'daily_hard_cap':CAP,'provider_daily_free_quota_observed':5000,'last_request':c.execute('select max(created) from ledger').fetchone()[0],'verified_within_1km':0,'free_only':True}
 (O/'baidu_geocoding_status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
 (O/'百度补充地址匹配进度.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="60"><title>百度补充地址匹配</title><style>body{font:17px sans-serif;max-width:950px;margin:40px auto;line-height:1.7}pre{white-space:pre-wrap;background:#eef3f8;padding:20px}</style><h1>百度补充地址匹配进度</h1><p>仅发送住址文字；行政区、道路和门牌核查后保留候选。坐标与实际精度仍需核验。每天最多4900次，达到上限保存断点；不购买服务。</p><pre>'+html.escape(json.dumps(s,ensure_ascii=False,indent=2))+'</pre>')
 print(json.dumps(s,ensure_ascii=False),flush=True)

def main():
 if __import__('os').environ.get('GEOCODING_AUTHORIZED') != 'YES':
  raise RuntimeError('External address geocoding is disabled until GEOCODING_AUTHORIZED=YES following data-custodian approval.')
 ap=argparse.ArgumentParser();ap.add_argument('--max-queries',type=int,default=0);args=ap.parse_args()
 fd=os.open(P/'baidu_geocoding.lock',os.O_CREAT|os.O_WRONLY,0o600)
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Another Baidu worker holds lock')
 db=P/'baidu_geocoding.sqlite';c=sqlite3.connect(db);c.execute('pragma journal_mode=WAL');c.executescript('create table if not exists queries(id text primary key,address text,ids text,stage text default "pending",reason text,selection text,response text);create table if not exists ledger(id integer primary key,day text,created text);');os.chmod(db,0o600)
 for r in csv.DictReader((P/'baidu_pending_addresses.csv').open(encoding='utf-8-sig')):c.execute('insert or ignore into queries(id,address,ids) values(?,?,?)',(r['local_query_id'],r['address'],r['local_location_ids']))
 c.commit();key=json.loads((P/'baidu_key.json').read_text());state='running';export(c,state)
 rows=c.execute('select id,address from queries where stage in ("pending","temporary_error") order by id').fetchall();rows=rows[:args.max_queries] if args.max_queries else rows
 try:
  for i,(qid,address) in enumerate(rows):
   variant=amap.building(amap.norm(address))
   if len(variant.encode())>128:variant=variant.removeprefix('广东省')
   if len(variant.encode())>128:c.execute('update queries set stage="unresolved",reason="address_exceeds_128_bytes" where id=?',(qid,));c.commit();continue
   res=None
   for attempt in range(3):
    day=now().date().isoformat()
    if c.execute('select count(*) from ledger where day=?',(day,)).fetchone()[0]>=CAP:state='waiting_daily_quota_reset';break
    c.execute('insert into ledger(day,created) values(?,?)',(day,now().isoformat()));c.commit()
    try:
     with urlopen(signed_url(variant,key),timeout=25) as f:res=json.load(f)
    except Exception:res={'status':-1,'message':'network_error'}
    time.sleep(.6)
    code=res.get('status')
    if code==0:break
    if code in (4,301,302):state='waiting_daily_quota_reset' if code in (4,302) else 'stopped_provider_quota';break
    if code not in (-1,1,401,402):state='stopped_provider_error_'+str(code);break
    time.sleep(2*(attempt+1))
   if state!='running':break
   sel,reason=select(variant,res)
   stage='selected' if sel else ('temporary_error' if res.get('status') in (-1,1,401,402) else 'unresolved')
   c.execute('update queries set stage=?,reason=?,selection=?,response=? where id=?',(stage,reason,json.dumps(sel,ensure_ascii=False) if sel else None,json.dumps(res,ensure_ascii=False),qid));c.commit()
   if i%100==0:export(c,state)
  if state=='running':state='pilot_finished' if args.max_queries else 'finished'
 except Exception:
  export(c,'stopped_local_error');raise
 export(c,state)
if __name__=='__main__':main()
