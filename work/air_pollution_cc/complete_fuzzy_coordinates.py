"""User-requested complete coordinate layer; distinguish candidate choices and location imputation.
Original provider exports/caches remain untouched. No additional external requests.
"""
import csv,json,sqlite3,re,math,os,subprocess,statistics,html
from pathlib import Path
from collections import defaultdict,Counter
from difflib import SequenceMatcher
import full_geocoding as g
P=g.P;O=g.O

def readcsv(name):return list(csv.DictReader((P/name).open(encoding='utf-8-sig')))
def db(name):
 c=sqlite3.connect('file:'+str(P/name)+'?mode=ro',uri=True);c.execute('begin');return c

def xy(value):
 try:
  x,y=map(float,str(value).split(','))
  return (x,y) if 112.5<x<114.7 and 22<y<24.8 else None
 except (ValueError,TypeError):return None

def tokens(address):
 d=g.district(address);t=address.split(d,1)[-1] if d else address.replace('广东省','').replace('广州市','')
 town=re.match(r'([\u4e00-\u9fff]{2,12}?(?:街道|镇))',t)
 town=town.group(1) if town else ''
 tail=t[len(town):] if town else t
 village=re.match(r'([\u4e00-\u9fff]{2,16}?(?:社区|村|小区|花园))',tail)
 return d,town,village.group(1) if village else ''

def candidate(address,point,text,provider,level='',extra=None,accepted=False):
 coords=xy(point)
 if not coords:return None
 d=g.district(address);td=g.district(text)
 if d and td and td!=d:return None
 a=g.norm(address);b=g.norm(text);road,nums=g.anchors(a);tr,tn=g.anchors(b)
 base=SequenceMatcher(None,re.sub('广东省|广州市','',a),re.sub('广东省|广州市','',b)).ratio()
 score=base+.2*bool(d and d in b)+.2*bool(road and any(r in b for r in road))+.2*bool(nums and nums[0] in tn)
 if nums and tn and nums[0]!=tn[0]:score-=.4
 if road and tr and not any(r in b for r in road):score-=.25
 if accepted:score+=2
 return {'gcj02_longitude':coords[0],'gcj02_latitude':coords[1],'provider':provider,'provider_level':str(level),'fuzzy_score':round(score,4),'accepted':accepted,'text':b}

def main():
 rows=readcsv('all_address_matching.csv');original_ids={r['location_id'] for r in rows}
 ca=db('full_geocoding.sqlite');addresses={qid:a for qid,a in ca.execute('select id,address from queries')}
 addr={r['location_id']:addresses.get(r['canonical_id'],'') for r in rows}
 for r in readcsv('baidu_pending_addresses.csv'):
  for lid in r['local_location_ids'].split('|'):addr[lid]=r['address']
 missing={r['location_id'] for r in rows if not r['longitude'] or not r['latitude']}
 pools=defaultdict(list)
 # Cache-only candidate retrieval, preserving every provider's original rejection decision.
 canonical_missing={r['canonical_id'] for r in rows if r['location_id'] in missing}
 bycanonical=defaultdict(list)
 for r in rows:
  if r['location_id'] in missing:bycanonical[r['canonical_id']].append(r['location_id'])
 wanted={addresses[c] for c in canonical_missing if c in addresses}
 wanted|={'search:'+g.fallback(addresses[c]) for c in canonical_missing if c in addresses and g.fallback(addresses[c])}
 cache={a:json.loads(v) for a,v in ca.execute('select address,result from responses') if a in wanted}
 for cid,lids in bycanonical.items():
  a=addresses.get(cid,'')
  for key in [a,'search:'+g.fallback(a)]:
   for p in cache.get(key,{}).get('geocodes',[]):
    text=str(p.get('formatted_address',''));ad=str(p.get('adcode',''))
    if ad and not ad.startswith('4401'):continue
    for lid in lids:
     v=candidate(addr[lid],p.get('location'),text,'amap',p.get('level',''))
     if v:pools[lid].append(v)
 for provider,name in [('baidu','baidu_geocoding.sqlite'),('tencent','tencent_geocoding.sqlite')]:
  c=db(name)
  for ids,stage,sel,response in c.execute('select ids,stage,selection,response from queries where response is not null'):
   lids=[x for x in ids.split('|') if x in missing]
   if not lids:continue
   r=json.loads(response);pnts=[]
   if stage=='selected' and sel:
    p=json.loads(sel);pnts.append((p.get('location'),p.get('formatted_address',''),p.get('level',''),True))
   if provider=='baidu' and r.get('status')==0:
    ps=r.get('poi_infos',[]) or [];ps=[ps] if isinstance(ps,dict) else ps
    for p in ps:
     if p.get('adcode') and not str(p['adcode']).startswith('4401'):continue
     loc=p.get('location',{});text=str(p.get('formatted_address',''))+str(p.get('name',''))
     pnts.append((str(loc.get('lng',''))+','+str(loc.get('lat','')),text,p.get('level',''),False))
    loc=r.get('result',{}).get('location',{});pnts.append((str(loc.get('lng',''))+','+str(loc.get('lat','')),'',r.get('result',{}).get('level',''),False))
   if provider=='tencent' and r.get('status')==0:
    p=r.get('result',{});ac=p.get('address_components',{});text=''.join(str(ac.get(k,'')) for k in ['province','city','district','street','street_number'])+str(p.get('title',''));loc=p.get('location',{})
    pnts.append((str(loc.get('lng',''))+','+str(loc.get('lat','')),text,p.get('level',''),False))
   for lid in lids:
    for loc,text,level,accepted in pnts:
     v=candidate(addr[lid],loc,text,provider,level,accepted=accepted)
     if v:pools[lid].append(v)
  c.close()
 # Derive transparent reference points from existing matched addresses; these are NOT official centroids.
 refs=defaultdict(list)
 for r in rows:
  if r['location_id'] in missing:continue
  try:x=float(r['longitude']);y=float(r['latitude'])
  except ValueError:continue
  if not (112.5<x<114.7 and 22<y<24.8):continue
  d,t,v=tokens(addr[r['location_id']])
  refs[('city',)].append((x,y))
  if d:refs[('district',d)].append((x,y))
  if d and t:refs[('town',d,t)].append((x,y))
  if d and t and v:refs[('village',d,t,v)].append((x,y))
 centers={}
 for key,values in refs.items():
  if len(values)>=3:centers[key]=(statistics.median(x for x,y in values),statistics.median(y for x,y in values),len(values))
 assert ('city',) in centers
 converted=[];result=[];kinds=Counter();providers=Counter()
 for r in rows:
  z=dict(r);lid=r['location_id'];z.update(original_coordinate_missing=int(lid in missing),coordinate_imputed=0,coordinate_source='existing_amap',fuzzy_level='existing_provider_match',reference_support_count='',fuzzy_candidate_score='',independently_verified_within_1km=0)
  if lid in missing:
   pool=sorted(pools[lid],key=lambda v:(v['fuzzy_score'],v['text'],v['provider']),reverse=True)
   best=pool[0] if pool else None
   # Weak/conflicting candidates are less defensible than an explicitly labelled reference location.
   if best and (best['accepted'] or best['fuzzy_score']>=.35):
    z.update(longitude='',latitude='',gcj02_longitude=best['gcj02_longitude'],gcj02_latitude=best['gcj02_latitude'],coordinate_source=best['provider'],match_method='supplement_screened_candidate' if best['accepted'] else 'cached_most_likely_fuzzy_candidate',match_quality='supplement_candidate_unverified' if best['accepted'] else 'fuzzy_candidate_unverified',fuzzy_level='screened_candidate' if best['accepted'] else 'fuzzy_candidate',coordinate_imputed=0 if best['accepted'] else 1,fuzzy_candidate_score=best['fuzzy_score'],provider_level=best['provider_level'],status='completed_candidate',verified_within_1km=0,crs='EPSG:4326')
    converted.append(z)
   else:
    d,t,v=tokens(addr[lid]);keys=[('village',d,t,v),('town',d,t),('district',d),('city',)]
    key=next(k for k in keys if k in centers);x,y,n=centers[key]
    z.update(longitude=x,latitude=y,gcj02_longitude='',gcj02_latitude='',coordinate_imputed=1,coordinate_source='local_matched_address_reference',match_method='matched_address_coordinate_median_reference',match_quality=key[0]+'_reference_imputed',fuzzy_level=key[0]+'_reference',reference_support_count=n,status='completed_reference_imputation',verified_within_1km=0,crs='EPSG:4326')
   kinds[z['fuzzy_level']]+=1;providers[z['coordinate_source']]+=1
  result.append(z)
 if converted:
  r=subprocess.run(['node',str(g.ROOT/'work/air_pollution_cc/convert_full_coordinates.cjs')],input=json.dumps(converted),text=True,capture_output=True,check=True)
  changes={x['location_id']:x for x in json.loads(r.stdout)}
  result=[changes.get(x['location_id'],x) for x in result]
 assert len(result)>0 and len({x['location_id'] for x in result})==152764 and original_ids=={x['location_id'] for x in result}
 assert all(math.isfinite(float(x['longitude'])) and math.isfinite(float(x['latitude'])) for x in result)
 assert all(x['longitude']==y['longitude'] and x['latitude']==y['latitude'] for x,y in zip(rows,result) if x['location_id'] not in missing)
 fn=P/'all_address_matching_completed.csv';tmp=fn.with_suffix('.tmp')
 with tmp.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
 os.chmod(tmp,0o600);tmp.replace(fn)
 summary={'created_at':__import__('baidu_geocoding').now().isoformat(),'total_original_addresses':len(result),'previously_without_coordinates':len(missing),'coordinate_rows_completed':len(result),'remaining_missing_longitude_latitude':0,'additional_by_level':dict(kinds),'additional_by_provider':dict(providers),'imputed_coordinate_rows':sum(int(x['coordinate_imputed']) for x in result),'independently_verified_within_1km':0,'additional_external_requests':0,'original_exports_unchanged':True,'snapshot_note':'Baidu and Tencent ongoing; this completed layer is a dated snapshot and does not stop their matching','district_city_reference_warning':'Reference points are medians of existing matched residential coordinates, not official administrative centroids or individual actual residences','tianditu_candidates_excluded_reason':'Provider CRS not independently verified yet; original 100 pilot preserved separately'}
 (O/'模糊定位补全汇总.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 (O/'模糊定位补全结果.html').write_text('<!doctype html><meta charset="utf-8"><title>模糊定位补全结果</title><style>body{font:17px sans-serif;max-width:1050px;margin:40px auto;line-height:1.8}pre{white-space:pre-wrap;background:#eef3f8;padding:20px}</style><h1>全量住址坐标补全</h1><p>全部152764条原始住址均有经纬度。优先保留原匹配坐标，再采用现有百度/腾讯已筛选候选、缓存中最可能候选；仍无法定位时按村社区、街镇、区、市逐级采用既有匹配地址坐标的中位数参考位置。这些填补坐标不是已核验的个体居住位置，也不是官方行政区中心。</p><p>原始匹配记录及未定位标记保留不变。新私有结果为all_address_matching_completed.csv，含original_coordinate_missing、coordinate_imputed、fuzzy_level、coordinate_source、reference_support_count等标记。经纬度无缺失不代表定位精确。区、市参考点会压缩空间暴露差异，应分别做敏感性分析，不能将其当成精确地址用于解释主结果。百度腾讯后台仍运行，可用后续更好候选更新此快照。</p><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>')
 print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
