"""Local reuse of explicit building/village/town anchors; never invent exact house locations.
Run only after external matching passes. Administrative references remain excluded from main models.
"""
import json,re,math
from collections import defaultdict

def apply(c,geo):
    houses=defaultdict(list);admin={};source_count=0
    def context(address):
        d=geo.district(address)
        town=re.search(r'([\u4e00-\u9fff]{2,10}(?:街道|镇))',re.sub('广东省|广州市|'+'|'.join(geo.DISTRICTS),'',address))
        return d,town.group(1) if town else ''
    for qid,address,sel in c.execute("SELECT id,address,selection FROM queries WHERE stage='selected'"):
        p=json.loads(sel);roads,nums=geo.anchors(address)
        if roads and nums and p.get('match_quality')=='door_or_building_unverified':houses[(context(address),roads[0],nums[0])].append(p)
    # Provider-declared village/town points only; no invented administrative centroids.
    for address,result in c.execute("SELECT address,result FROM responses WHERE address NOT LIKE 'search:%'"):
        r=json.loads(result)
        if r.get('status')!='1':continue
        for p in r.get('geocodes',[]):
            formatted=geo.norm(str(p.get('formatted_address','')));d=geo.district(formatted)
            if not d or not str(p.get('adcode','')).startswith('4401') or p.get('level') not in ('村庄','乡镇'):continue
            if not p.get('location'):continue
            # Full administrative prefix is required, preventing cross-district name reuse.
            prefix=formatted.replace('广东省','')
            prefix=re.sub(r'[\d].*$','',prefix)
            if p.get('level')=='村庄' and '村' not in prefix:continue
            if p.get('level')=='乡镇' and not re.search(r'街道|镇',prefix):continue
            if len(prefix)<9:continue
            old=admin.get(prefix)
            if old and old.get('location')!=p.get('location'):admin[prefix]=None
            elif prefix not in admin:admin[prefix]=p
    bydistrict=defaultdict(list)
    for prefix,p in admin.items():
        if p:bydistrict[geo.district(prefix)].append((prefix,p))
    for values in bydistrict.values():values.sort(key=lambda x:len(x[0]),reverse=True)
    count=0;kind=defaultdict(int)
    for qid,address,stage in c.execute("SELECT id,address,stage FROM queries WHERE stage IN ('unresolved','needs_fuzzy','pending','temporary_error')").fetchall():
        chosen=None;roads,nums=geo.anchors(address)
        if roads and nums:
            group=houses.get((context(address),roads[0],nums[0]),[])
            if group:
                coords=[tuple(map(float,p['location'].split(','))) for p in group]
                # Same explicit house anchor, all source coordinates within roughly 100 m.
                if max(x for x,y in coords)-min(x for x,y in coords)<.0008 and max(y for x,y in coords)-min(y for x,y in coords)<.0008:
                    chosen=dict(group[0],match_method='local_same_road_house_anchor',match_quality='building_anchor_reuse_unverified',verified_within_1km=0)
        if not chosen:
            text=geo.norm(address).replace('广东省','')
            for prefix,p in bydistrict.get(geo.district(address),[]):
                if prefix in text:
                    chosen=dict(p,match_method='local_explicit_administrative_anchor',match_quality='village_reference_only' if p['level']=='村庄' else 'township_reference_only',match_score=0,candidate_margin=0,verified_within_1km=0);break
        if chosen:
            c.execute('UPDATE queries SET stage=?,selection=?,reason=? WHERE id=?',('approximate',json.dumps(chosen,ensure_ascii=False),'approximate_reference_excluded_from_main_analysis',qid));count+=1;kind[chosen['match_quality']]+=1
    c.commit();return {'local_additional_approximate_queries':count,'local_additional_by_quality':dict(kind)}
