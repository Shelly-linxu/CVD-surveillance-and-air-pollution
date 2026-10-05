"""Cache-only address consistency audit. Never certifies positional accuracy."""
import csv,json,sqlite3,re,math,os,html
from collections import Counter,defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import full_geocoding as g
P,O=g.P,g.O

def read(n):
 with (P/n).open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def database(n):
 c=sqlite3.connect('file:'+str(P/n)+'?mode=ro',uri=True);c.execute('begin');return c

def point(s):
 try:
  a,b=map(float,str(s).split(','));return (a,b) if math.isfinite(a+b) else None
 except (ValueError,TypeError):return None

def distance(a,b):
 return 6371008.8*2*math.asin(min(1,math.sqrt(math.sin(math.radians(b[1]-a[1])/2)**2+math.cos(math.radians(a[1]))*math.cos(math.radians(b[1]))*math.sin(math.radians(b[0]-a[0])/2)**2)))

def compact(p,provider):
 q=point(p.get('location'))
 if not q:return None
 return {'xy':q,'text':g.norm(str(p.get('formatted_address',''))),'adcode':str(p.get('adcode','')),'provider':provider,'level':str(p.get('level',''))}

def signatures(s):
 s=g.norm(s);roads,_=g.anchors(s)
 house=re.findall(r'(?<!\d)(\d+(?:-\d+)?)(?:号)(?!楼|栋|幢)',s)
 building=re.findall(r'(?<!\d)([A-Za-z]?\d+|[A-Za-z])(?:栋|幢|座)',s)
 return roads,house,building

def check(a,p):
 text=p['text'];d=g.district(a);td=g.district(text)
 if not td:td=next((k for k,v in g.DISTRICTS.items() if p['adcode']==v),'')
 r,h,b=signatures(a);tr,th,tb=signatures(text)
 road_agree=bool(r and any(x in text or any(x.endswith(y) or y.endswith(x) for y in tr) for x in r))
 return {'district_conflict':int(bool(d and td and d!=td)), 'district_evidence_missing':int(bool(d and not td)),
 'road_conflict':int(bool(r and tr and not road_agree)), 'road_evidence_missing':int(bool(r and not tr)),
 'house_number_conflict':int(bool(h and th and h[0]!=th[0])), 'house_number_evidence_missing':int(bool(h and not th)),
 'building_number_conflict':int(bool(b and tb and b[0]!=tb[0])), 'building_number_evidence_missing':int(bool(b and not tb)),
 'road_agree':int(road_agree),'house_number_agree':int(bool(h and th and h[0]==th[0])), 'building_number_agree':int(bool(b and tb and b[0]==tb[0]))}

FLAGS=['district_conflict','district_evidence_missing','road_conflict','road_evidence_missing','house_number_conflict','house_number_evidence_missing','building_number_conflict','building_number_evidence_missing','road_agree','house_number_agree','building_number_agree']

def main():
 rows=read('all_address_matching_completed.csv');c=database('full_geocoding.sqlite')
 queries={qid:(a,json.loads(s) if s else None) for qid,a,s in c.execute('select id,address,selection from queries')}
 addresses={r['location_id']:queries.get(r['canonical_id'],('',None))[0] for r in rows}
 # Normalized request preserves house/building anchors; final room removal is separately recorded.
 normalized={r['location_id']:r['address'] for r in read('geocoding_normalized_queries_v2.csv')}
 room={r['location_id']:r['terminal_room_removed'] for r in read('geocoding_normalized_map_v2.csv')}
 for r in rows:addresses[r['location_id']]=normalized.get(r['query_id'],addresses[r['location_id']])
 for r in read('baidu_pending_addresses.csv'):
  for lid in r['local_location_ids'].split('|'):addresses[lid]=r['address']
 cache={}
 for a,v in c.execute('select address,result from responses'):
  vals=[]
  for p in json.loads(v).get('geocodes',[]):
   z=compact(p,'amap')
   if z:vals.append(z)
  if vals:cache[a]=vals
 supplemental=defaultdict(list)
 for provider,n in [('baidu','baidu_geocoding.sqlite'),('tencent','tencent_geocoding.sqlite')]:
  db=database(n)
  for ids,sel,response in db.execute('select ids,selection,response from queries where response is not null'):
   vals=[]
   if sel:
    z=compact(json.loads(sel),provider)
    if z:vals.append(z)
   rsp=json.loads(response)
   if provider=='baidu' and rsp.get('status')==0:
    ps=rsp.get('poi_infos',[]) or [];ps=[ps] if isinstance(ps,dict) else ps
    for p in ps:
     loc=p.get('location',{});q=dict(p,location=f"{loc.get('lng','')},{loc.get('lat','')}",formatted_address=str(p.get('formatted_address',''))+str(p.get('name','')))
     z=compact(q,provider)
     if z:vals.append(z)
   elif provider=='tencent' and rsp.get('status')==0:
    p=rsp.get('result',{});loc=p.get('location',{});ac=p.get('address_components',{})
    text=''.join(str(ac.get(k,'')) for k in ['province','city','district','street','street_number'])+str(p.get('title',''))
    z=compact(dict(p,location=f"{loc.get('lng','')},{loc.get('lat','')}",formatted_address=text,adcode=p.get('ad_info',{}).get('adcode','')),provider)
    if z:vals.append(z)
   for lid in ids.split('|'):supplemental[lid].extend(vals)
  db.close()
 counts=Counter();flags=Counter();groups=Counter();door=Counter();review=[];result=[]
 for row in rows:
  z=dict(row);lid=row['location_id'];a=addresses[lid];canonical=queries.get(row['canonical_id'],('',None));request=canonical[0]
  vals=list(cache.get(request,[]))+list(cache.get('search:'+g.fallback(request),[]))+supplemental.get(lid,[])
  if canonical[1]:
   p=compact(canonical[1],'amap')
   if p:vals.append(p)
  # Exact cache duplicates are not distinct alternatives.
  vals=list({(v['provider'],v['xy'],v['text']):v for v in vals}.values())
  level=row['provider_level'];quality=row['match_quality'];fuzzy=row['fuzzy_level']
  if 'city_reference' in fuzzy:category='city_reference'
  elif 'district_reference' in fuzzy:category='district_reference'
  elif 'town_reference' in fuzzy or 'township_reference' in quality or level in ('乡镇','街道'):category='township_street_reference'
  elif 'village_reference' in fuzzy or 'village_reference' in quality or level=='村庄':category='village_community_reference'
  elif level in ('门牌号','门址','9') or 'door_or_building' in quality or 'building_anchor' in quality:category='door_building_candidate'
  elif level in ('10','11') or level in ('住宅区','商务住宅','楼宇'):category='building_poi_candidate'
  elif level in ('道路','路','7'):category='road_reference'
  else:category='fuzzy_candidate'
  reference=category.endswith('reference');q=point(str(row['gcj02_longitude'])+','+str(row['gcj02_latitude']))
  same=[p for p in vals if q and distance(q,p['xy'])<=2 and p['provider']==row['coordinate_source'].replace('existing_','')]
  # Choose evidence closest to the actual saved coordinate, not a newer unrelated selection.
  chosen=max(same,key=lambda p:g.score(a,{'formatted_address':p['text'],'adcode':p['adcode']})[0]) if same else None
  evidence=check(a,chosen) if chosen else {k:0 for k in FLAGS}
  conflict=any(evidence[k] for k in ['district_conflict','road_conflict','house_number_conflict','building_number_conflict'])
  inputroad,inputhouse,inputbuilding=signatures(a)
  passed=bool(chosen and not conflict and not evidence['district_evidence_missing'] and evidence['road_agree'] and ((inputhouse and evidence['house_number_agree']) or (inputbuilding and evidence['building_number_agree'])) and not evidence['house_number_evidence_missing'] and not evidence['building_number_evidence_missing'])
  plausible=[]
  for p in vals:
   e=check(a,p)
   if any(e[k] for k in ['district_conflict','road_conflict','house_number_conflict','building_number_conflict']):continue
   if inputroad and not e['road_agree']:continue
   if inputhouse and not e['house_number_agree']:continue
   if inputbuilding and not e['building_number_agree']:continue
   if not p['text']:continue
   plausible.append(p)
  clusters=[]
  for p in plausible:
   if not any(distance(p['xy'],xy)<=100 for xy in clusters):clusters.append(p['xy'])
  spread=max((distance(x,y) for i,x in enumerate(clusters) for y in clusters[i+1:]),default=0)
  ambiguous=len(clusters)>1
  disposition='reference_only' if reference else 'address_conflict' if conflict else 'multiple_plausible_locations' if ambiguous else 'text_consistent_spatial_unverified' if passed else 'insufficient_address_evidence'
  priority=1 if (category=='door_building_candidate' and (conflict or ambiguous)) else 2 if (conflict or ambiguous or category in ('door_building_candidate','building_poi_candidate') and not passed) else 3 if reference or not passed else 4
  z.update(audit_category=category,is_fuzzy_match=int('fuzzy' in quality or fuzzy=='fuzzy_candidate' or category=='fuzzy_candidate'),is_street_or_road_reference=int(category in ('township_street_reference','road_reference')),is_area_reference=int(category in ('city_reference','district_reference','village_community_reference')),is_building_anchor_reuse=int('building_anchor' in quality),candidate_evidence_found=int(chosen is not None),**evidence,cached_candidate_count=len(vals),plausible_location_clusters_100m=len(clusters),multiple_plausible_locations=int(ambiguous),plausible_candidate_max_separation_m=round(spread),textual_door_building_consistency_pass=int(passed),audit_disposition=disposition,review_priority=priority,terminal_room_removed=room.get(lid,''),independently_verified_within_1km=0)
  result.append(z);groups[category]+=1;counts[disposition]+=1
  for k in FLAGS+['multiple_plausible_locations','is_fuzzy_match','is_street_or_road_reference','is_area_reference','candidate_evidence_found']:flags[k]+=int(z[k])
  if category in ('door_building_candidate','building_poi_candidate'):door[disposition]+=1
  if priority<=2:review.append({k:z[k] for k in ['location_id','coordinate_source','audit_category','review_priority','audit_disposition']+FLAGS+['plausible_location_clusters_100m','plausible_candidate_max_separation_m']})
 assert len(result)>0 and len({r['location_id'] for r in result})==len(result)
 assert all(r['longitude']==s['longitude'] and r['latitude']==s['latitude'] for r,s in zip(result,rows))
 assert sum(groups.values())==len(result)
 for name,data in [('all_address_matching_quality_checked.csv',result),('address_priority_review_queue.csv',sorted(review,key=lambda r:r['review_priority']))]:
  path=P/name;tmp=path.with_suffix('.tmp')
  with tmp.open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(data[0]) if data else ['location_id']);w.writeheader();w.writerows(data)
  os.chmod(tmp,0o600);tmp.replace(path)
 summary={'checked_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'total_rows':len(result),'coordinates_preserved':True,'missing_coordinates':0,'category_counts':dict(groups),'audit_disposition_counts':dict(counts),'audit_flag_counts':dict(flags),'door_building_audit':dict(door),'priority_1_2_review_rows':len(review),'independently_verified_within_1km':0,'additional_external_requests':0,'method_notes':['仅核查现有缓存中与已保存坐标相距不超过2米的同供应商候选文字；未找到候选证据则标记不足。','门牌与栋幢座数字分别比较；道路按文字包含或后缀一致核查，行政区优先采用文字及返回区代码。名称相似并不证明建筑物一致。','候选必须与输入道路、门牌、栋幢座及行政区已有证据不冲突，且所需道路及数字明确一致；相隔超过100米的候选位置另列多候选标记。100米为复核阈值，不是准确度认证。','缺少门牌/栋幢座或具体道路证据的建筑物候选保留待人工核验；参考点单独分类。','全部坐标保留，原始结果不覆盖；文字一致不代表实际居住地或1公里精度已核验。','核验时使用各供应商缓存快照，后台新增候选可能形成新复核线索。']}
 (O/'地址匹配质量核验汇总.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 content='<h1>地址匹配质量核验</h1><p>全部152764条坐标保留，无经纬度缺失。门牌、建筑物候选优先复核；文字一致仅代表缓存证据支持，不代表实际空间精度已认证。模糊匹配、街道/道路、村社区和区市参考点分别标记。</p>'
 for title,data in [('位置类别',groups),('门牌及建筑物核验',door)]:
  content+='<h2>'+title+'</h2><table>'+''.join('<tr><td>'+html.escape(k)+'</td><td>'+str(v)+'</td></tr>' for k,v in data.items())+'</table>'
 content+='<h2>核验方法及限制</h2><ul>'+''.join('<li>'+html.escape(n)+'</li>' for n in summary['method_notes'])+'</ul><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>'
 (O/'地址匹配质量核验报告.html').write_text('<!doctype html><meta charset="utf-8"><title>地址匹配质量核验</title><style>body{font:17px sans-serif;max-width:1050px;margin:40px auto;line-height:1.8}td{border-bottom:1px solid #ddd;padding:8px 20px}pre{white-space:pre-wrap;background:#eef3f8;padding:20px}</style>'+content)
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
