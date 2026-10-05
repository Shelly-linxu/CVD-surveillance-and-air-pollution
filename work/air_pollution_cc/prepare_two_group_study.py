"""Human-requested broad registry analysis. Does not override event adjudication."""
from pathlib import Path
import csv,gzip,json,os,hashlib
from collections import Counter
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'work/air_pollution_cc/private';Q=P/'two_group';O=ROOT/'outputs/air_pollution_cc/two_group'
def read(p):
    op=gzip.open if p.suffix=='.gz' else open
    with op(p,'rt',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(path,rr):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
def main():
    Q.mkdir(parents=True,exist_ok=True);O.mkdir(parents=True,exist_ok=True);os.chmod(Q,0o700)
    if (Q/'event_adjudication.csv').exists():raise RuntimeError('Existing two-group snapshot preserved')
    ad={r['event_id']:r for r in read(P/'event_adjudication.csv')};rr=[]
    for e in read(P/'candidate_events.csv.gz'):
        pre=e['icd10'][:3];group='CVD' if pre in ['I20','I21','I22','I46'] else 'CBVD' if pre in ['I60','I61','I63','I64'] else ''
        assert group
        a=dict(ad[e['event_id']]);a.update(location_id=e['location_id'],icd10=e['icd10'],icd_prefix=pre,onset=e['onset'],age=e['age'],sex=e['sex'],season=e['season'],year=e['year'],study_group=group,registry_analysis_inclusion=1,scope_version='two_group_registry_v1_20261003')
        a['strict_event_approved']=int(a['decision']=='included' and a['eligible']=='1' and a['dedup_finalized']=='1')
        a['scope_note']='全部监测报告分析，不解除既有未决事件资格；非经审定急性结局'
        rr.append(a)
    save(Q/'event_adjudication.csv',rr);os.chmod(Q/'event_adjudication.csv',0o600)
    counts=Counter((r['study_group'],r['icd_prefix'],r['year'],r['decision']) for r in rr)
    summary=[dict(group=g,icd_prefix=c,year=y,adjudication_status=d,n=n) for (g,c,y,d),n in sorted(counts.items())];save(O/'两类疾病原始候选与审定状态.csv',summary)
    plan={'version':'two_group_registry_v1_20261003','created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'user_requested_scope':'全部心脑血管候选事件，两类疾病分别分析；不随机抽样到15万','candidate_events':len(rr),'groups':{'CVD':{'name':'心血管监测报告事件','ICD':['I20','I21','I22','I46'],'definition_limit':'I20可能包含稳定/慢性心绞痛，I46需核实猝死定义；不得将所有报告等同于审定急性冠脉事件'},'CBVD':{'name':'脑血管监测报告事件','ICD':['I60','I61','I63','I64'],'definition_limit':'含未特指卒中；编码/文字及事件资格未决者不因此自动确诊'}},'design':'同年同月同星期几，事件自身对照，原始固定日历不变','main_registry_sample':'全部候选报告事件及全部坐标层，包括模糊、粗定位和插补坐标；探索性，不能称为已验证1km主分析','address_sensitivities':['exclude_coordinate_imputation','text_consistent_core','core_plus_coarse_reference'],'event_sensitivities':['final_review_status_only','strict_previous_adjudication','exclude_identity_anomalies','exclude_duplicate_and_short_interval_flags','first_person_per_group_record','restrict_acute_code_scope'],'acute_code_scope':{'CVD':['I21','I22','I20.0'],'CBVD':['I60','I61','I63']},'primary_window':'lag01','windows':['lag0','lag1','lag2','lag3','lag02','lag03','lag12'],'temperature_configs':['main_lag21_df3x3','lag14','lag28','df4'],'humidity':'lag03,df3','variance':'按个人聚类稳健方差；时间块方差另行检查','holiday':'法定节日及调休；放假区间替代敏感性','missingness':'任何固定候选日期或协变量缺失，整组排除；不插补污染、不补选对照','common_sample':'同一污染物所有预设污染窗口的共同完整事件组','two_pollutant':['PM25+O3','PM10+O3'],'interactions':['age65','male','warm'],'multiple_testing':'每类研究三种污染物lag01分别作BH校正，均为探索性；其他敏感性与扩展结果不混入该集合','previous_MI_exploratory_associations_seen':True,'revision_reason':'用户在MI探索结果后明确要求全部事件、两类研究和追加敏感性分析；本版不是事前注册','parameters_fixed_before_this_new_two_group_estimation':True,'original_adjudication_unchanged':True,'formal_primary_analysis_ready':False}
    (O/'两类疾病分析方案_v1.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    assert len(rr)>0
    result={'events':len(rr),'by_group':dict(Counter(r['study_group'] for r in rr)),'strictly_approved_by_group':dict(Counter(r['study_group'] for r in rr if r['strict_event_approved'])),'study_status':'registry_exploratory_with_flagged_sample_sensitivities'}
    (O/'研究范围汇总.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
