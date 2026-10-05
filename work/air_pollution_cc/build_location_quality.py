"""Assign address analysis eligibility without promoting unverified precision."""
import csv,json,math,os,html
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'work/air_pollution_cc/private';O=ROOT/'outputs/air_pollution_cc'
CONFLICT=['district_conflict','road_conflict','house_number_conflict','building_number_conflict']

def main():
 with (P/'all_address_matching_quality_checked.csv').open(encoding='utf-8-sig') as f:source=list(csv.DictReader(f))
 rows=[];tiers=Counter();totals=Counter()
 for r in source:
  valid=r['crs']=='EPSG:4326' and all(math.isfinite(float(r[k])) for k in ['longitude','latitude'])
  flags=[k for k in CONFLICT if r[k]=='1']
  ambiguous=r['multiple_plausible_locations']=='1'
  consistent=r['audit_disposition']=='text_consistent_spatial_unverified'
  precise_type=r['audit_category'] in ['door_building_candidate','building_poi_candidate']
  independent=r['independently_verified_within_1km']=='1'
  main_ok=valid and precise_type and consistent and independent and not flags and not ambiguous
  primary_candidate=valid and precise_type and consistent and not independent and not flags and not ambiguous
  core=valid and consistent and not flags and not ambiguous
  coarse=valid and r['audit_category'] in ['road_reference','township_street_reference','village_community_reference'] and r['candidate_evidence_found']=='1' and r['district_evidence_missing']=='0' and not flags and not ambiguous and r['coordinate_source']!='local_matched_address_reference'
  reasons=[]
  if not valid:reasons.append('invalid_coordinate_or_crs')
  if flags:reasons.extend(flags)
  if ambiguous:reasons.append('multiple_plausible_locations')
  if r['candidate_evidence_found']!='1':reasons.append('saved_coordinate_candidate_evidence_missing')
  if r['audit_category'] in ['city_reference','district_reference'] or r['coordinate_source']=='local_matched_address_reference':
   tier='excluded_reference_imputation';reasons.append('reference_imputation_not_individual_residence')
  elif main_ok:tier='main_qualified'
  elif primary_candidate:tier='primary_candidate_pending_spatial_validation';reasons.append('within_1km_not_verified')
  elif core:tier='sensitivity_text_consistent_fuzzy';reasons.append('unverified_or_fuzzy_candidate')
  elif coarse:tier='sensitivity_coarse_reference';reasons.append('coarse_reference_position_only')
  else:tier='excluded_pending_quality_review';reasons.append('address_consistency_or_specificity_insufficient')
  if tier.startswith('excluded_'):main_ok=primary_candidate=core=coarse=False
  sens=core or coarse
  row={k:r[k] for k in ['location_id','longitude','latitude','crs','coordinate_source','provider_level','match_method','match_quality','original_coordinate_missing','coordinate_imputed','fuzzy_level','audit_category','audit_disposition','review_priority','candidate_evidence_found','is_fuzzy_match','is_street_or_road_reference','is_area_reference','is_building_anchor_reuse']+CONFLICT+['district_evidence_missing','road_evidence_missing','house_number_evidence_missing','building_number_evidence_missing','multiple_plausible_locations','plausible_location_clusters_100m','plausible_candidate_max_separation_m']}
  row.update(verified_within_1km=int(main_ok),independently_verified_within_1km=int(independent),main_eligible=int(main_ok),primary_candidate_pending_validation=int(primary_candidate),sensitivity_eligible=int(sens),sensitivity_core_eligible=int(core),sensitivity_coarse_eligible=int(coarse),analysis_tier=tier,eligibility_reason=';'.join(dict.fromkeys(reasons)) or 'validated_precise_address',main_exclusion_reason='' if main_ok else ';'.join(dict.fromkeys(reasons+(['within_1km_not_verified'] if not independent else []))),sensitivity_plan='core_unverified_candidates' if core else 'expanded_coarse_reference_separate_run' if coarse else 'excluded_until_review',quality_rule_version='location_quality_v1_20261003')
  rows.append(row);tiers[tier]+=1
  for k in ['main_eligible','primary_candidate_pending_validation','sensitivity_eligible','sensitivity_core_eligible','sensitivity_coarse_eligible']:totals[k]+=row[k]
 target=P/'location_quality.csv';tmp=target.with_suffix('.tmp')
 with tmp.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 os.chmod(tmp,0o600);tmp.replace(target)
 assert len(rows)>0 and len({r['location_id'] for r in rows})==len(rows)
 assert all(a['longitude']==b['longitude'] and a['latitude']==b['latitude'] for a,b in zip(rows,source))
 assert all(r['main_eligible']==r['verified_within_1km'] for r in rows)
 assert all(not r['main_eligible'] or r['independently_verified_within_1km'] for r in rows)
 assert all(not r['sensitivity_eligible'] or not any(r[k]=='1' for k in CONFLICT+['multiple_plausible_locations']) for r in rows)
 assert totals['sensitivity_eligible']==totals['sensitivity_core_eligible']+totals['sensitivity_coarse_eligible']
 summary={'created_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'input_snapshot':'all_address_matching_quality_checked.csv','output_private_file':'work/air_pollution_cc/private/location_quality.csv','rows':len(rows),'eligibility_counts':dict(totals),'tier_counts':dict(tiers),'rules':{'main':'门牌/建筑物候选文字一致，无冲突及多个可能位置，并已独立核验约1km精度；当前无地址达到这一最终条件。','primary_candidate':'门牌/建筑物文字一致、无冲突及多个可能位置，优先进入空间精度复核；不等于主分析合格。','sensitivity_core':'文字一致、无冲突及多个可能位置的未核验候选；主分析候选也可进入这一独立敏感性分析。','sensitivity_coarse':'道路、街镇、村社区参考点有缓存候选证据、行政区证据完整，无冲突及多个可能位置；须另行开展扩展敏感性分析，不能默认混入核心样本。','excluded':'区市参考点、本地中位数插补点，以及其他冲突、多候选或地址证据不足者暂不纳入关联模型；坐标仍完整保留。'},'notes':['计数单位为唯一原始地址，不是病例人数或事件数。','verified_within_1km与main_eligible保持一致，兼容现有fit_models.R主分析筛选接口。','所有经纬度原样保留、无缺失；不改变既有核验或原始供应商结果。','本文件不是新增空间验证；主分析候选需人工或独立空间证据复核后更新。'],'validation':{'unique_location_ids':True,'coordinates_preserved':True,'missing_coordinates':0,'eligibility_consistent':True,'output_permissions':'0600'}}
 (O/'location_quality_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 labels={'main_eligible':'主分析正式合格','primary_candidate_pending_validation':'主分析候选：待精度复核','sensitivity_core_eligible':'核心敏感性分析','sensitivity_coarse_eligible':'扩展敏感性分析：粗定位参考点','sensitivity_eligible':'敏感性分析合计'}
 content='<h1>地址分析资格</h1><p>location_quality.csv已生成，全部152764条原始地址坐标保留。主分析正式资格与待核验候选明确区分；敏感性分析按候选地址和粗定位参考点分别运行。</p><table>'+''.join('<tr><td>'+labels[k]+'</td><td>'+str(v)+'</td></tr>' for k,v in totals.items())+'</table><h2>判定规则</h2><ul>'+''.join('<li>'+html.escape(v)+'</li>' for v in summary['rules'].values())+'</ul><p>计数为地址数，不是病例数。无坐标缺失不代表全部适合统计模型。</p><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>'
 (O/'地址主分析与敏感性分析资格.html').write_text('<!doctype html><meta charset="utf-8"><title>地址分析资格</title><style>body{font:17px sans-serif;max-width:1000px;margin:40px auto;line-height:1.8}td{padding:8px 20px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;background:#eef3f8;padding:20px}</style>'+content)
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
