"""Evidence-limited adjudication; pending rows remain explicitly unresolved.
Does not alter source workbooks, earlier candidate tables, or a frozen protocol.
"""
import csv,gzip,json,re,os,hashlib,hmac
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
from openpyxl import load_workbook
from prepare_cases import ROOT,SOURCES,dt,text
from audit_identity import classify,WEIGHTS,CHECK

P=ROOT/'work/air_pollution_cc/private';O=ROOT/'outputs/air_pollution_cc/event_adjudication'
VERSION='event_adjudication_v1_20261003'
def read(path):
    op=gzip.open if path.suffix=='.gz' else open
    with op(path,'rt',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def canonical(s):
    if re.fullmatch(r'\d{15}',s):
        q=s[:6]+'19'+s[6:];return q+CHECK[sum(int(x)*w for x,w in zip(q,WEIGHTS))%11]
    return s
def main():
    O.mkdir(parents=True,exist_ok=True)
    target=P/'event_adjudication.csv'
    if target.exists():raise RuntimeError('Existing adjudication file preserved; explicit versioned update required')
    candidates={r['event_id']:r for r in read(P/'candidate_events.csv.gz')}
    annotations={r['event_id']:r for r in read(P/'event_outcome_candidates.csv.gz')}
    salt=(P/'id_salt.bin').read_bytes()
    def token(s):return hmac.new(salt,s.encode(),hashlib.sha256).hexdigest()[:24]
    raw=[];allids=defaultdict(list);cardgroups=defaultdict(list);stats=Counter()
    for year,fn,sheet in SOURCES:
        wb=load_workbook(ROOT/'原始数据'/fn,read_only=True,data_only=True);it=wb[sheet].iter_rows(values_only=True);head=list(next(it));idx={v:i for i,v in enumerate(head)}
        def get(row,*keys):
            return next((row[idx[k]] for k in keys if k in idx),None)
        for rn,row in enumerate(it,2):
            if all(v is None for v in row):continue
            eid=f'E{year}_{rn:07d}';s=text(get(row,'身份证号')).upper();label,idbirth,idsex=classify(s);birth=dt(get(row,'出生日期'));onset=dt(get(row,'发病日期'));dx=dt(get(row,'诊断日期'));reported=dt(get(row,'报告日期'));sex=text(get(row,'性别'));code=text(get(row,'ICD10')).upper();prefix=code[:3];review=text(get(row,'审核状态','卡片状态'));diagnosis=text(get(row,'诊断'))
            valid=idbirth is not None
            cid=token('canonical_person:'+canonical(s)) if valid else ''
            originalpid=token('person:'+s) if s else ''
            card=text(get(row,'报告卡编号'));parts=[text(get(row,*keys)) for keys in [('现住地址（省）','现住址省'),('现住地址（市）','现住址市'),('现住地址（区县）','现住址区县'),('现住地址（街道/乡）','现住址街道'),('现住地址（居委会/村）','现住址居委会'),('现住地址（门牌号）','现住址号')]]
            r={'event_id':eid,'year':year,'person_id':originalpid,'canonical_person_id':cid,'onset':onset.isoformat() if onset else '', 'icd10':code,'icd_prefix':prefix,'review_status':review,'duplicate_flag':text(get(row,'是否重卡')),'first_onset_flag':text(get(row,'是否首次发病')),'id_check':label,'id_dob_conflict':int(valid and birth is not None and birth!=idbirth),'id_sex_conflict':int(valid and sex not in ('男','女') or valid and sex!=idsex),'id_numeric_storage':int(isinstance(get(row,'身份证号'),(int,float))),'candidate_present':int(eid in candidates),'location_hash':token('location:'+''.join(parts)),'diagnosis_before_onset':int(bool(dx and onset and dx<onset)),'report_before_onset':int(bool(reported and onset and reported<onset)),'chronic_diagnosis_flag':int(bool(re.search('陈旧性|后遗症|恢复期|康复期',diagnosis))),'card_token':token('card:'+card) if card else ''}
            raw.append(r)
            if cid:allids[cid].append(r)
            if card:cardgroups[(year,r['card_token'])].append(r)
        wb.close();print('Raw review completed',year,flush=True)
    # Date of birth/sex disagreement across a shared valid canonical identifier.
    canonical_oldtokens=defaultdict(set)
    for cid,rr in allids.items():
        canonical_oldtokens[cid]={r['person_id'] for r in rr}
    episodegroups=defaultdict(list)
    for r in raw:
        if r['canonical_person_id'] and r['onset'] and r['icd_prefix'] in ['I20','I21','I22','I60','I61','I63','I64']:
            episodegroups[(r['canonical_person_id'],r['icd_prefix'])].append(r)
    near=set();pairrows=[];ep=0
    for (cid,prefix),rr in episodegroups.items():
        rr.sort(key=lambda r:(r['onset'],r['event_id']));prev=None;anchor=None
        for r in rr:
            d=datetime.fromisoformat(r['onset']).date()
            gap=(d-datetime.fromisoformat(prev['onset']).date()).days if prev else None
            if anchor is None or (d-anchor).days>28:ep+=1;anchor=d
            r['monitoring_episode_id']=f'M{ep:07d}';r['days_since_previous_same_prefix']='' if gap is None else gap
            r['previous_same_prefix_event_id']=prev['event_id'] if prev else ''
            if prev and gap<=28:
                near.update([r['event_id'],prev['event_id']]);pairrows.append({'previous_event_id':prev['event_id'],'current_event_id':r['event_id'],'person_id':cid,'icd_prefix':prefix,'previous_onset':prev['onset'],'current_onset':r['onset'],'gap_days':gap,'address_conflict':int(prev['location_hash']!=r['location_hash']),'full_icd_conflict':int(prev['icd10']!=r['icd10']),'cross_year':int(prev['year']!=r['year']),'classification':'same_day_duplicate_candidate' if gap==0 else 'within28_monitoring_episode_candidate','action':'pending_source_record_review'})
            prev=r
    # Cross subtype pairs are reviewed rather than collapsed using outcome labels.
    broad=defaultdict(list)
    for r in raw:
        if r['canonical_person_id'] and r['onset']:
            family='AMI' if r['icd_prefix'] in ['I21','I22'] else 'stroke' if r['icd_prefix'] in ['I60','I61','I63','I64'] else ''
            if family:broad[(r['canonical_person_id'],family)].append(r)
    subtype_near=set()
    for key,rr in broad.items():
        rr.sort(key=lambda r:(r['onset'],r['event_id']))
        for i,r in enumerate(rr):
            for old in reversed(rr[:i]):
                gap=(datetime.fromisoformat(r['onset'])-datetime.fromisoformat(old['onset'])).days
                if gap>28:break
                if old['icd_prefix']!=r['icd_prefix']:
                    subtype_near.update([old['event_id'],r['event_id']]);pairrows.append({'previous_event_id':old['event_id'],'current_event_id':r['event_id'],'person_id':key[0],'icd_prefix':key[1],'previous_onset':old['onset'],'current_onset':r['onset'],'gap_days':gap,'address_conflict':int(old['location_hash']!=r['location_hash']),'full_icd_conflict':1,'cross_year':int(old['year']!=r['year']),'classification':'cross_prefix_short_interval','action':'pending_source_record_review'})
    candidate_raw=[r for r in raw if r['candidate_present']]
    final=[];full=[]
    for r in raw:
        eid=r['event_id'];ann=annotations.get(eid,{});outcome=ann.get('proposed_outcome','');flags=[]
        if r['review_status']!='已终审':flags.append('REVIEW_REJECTED' if '不通过' in r['review_status'] else 'REVIEW_INCOMPLETE')
        if not r['canonical_person_id']:flags.append('IDENTITY_INVALID')
        if r['id_dob_conflict']:flags.append('IDENTITY_DOB_CONFLICT')
        if r['id_sex_conflict']:flags.append('IDENTITY_SEX_CONFLICT')
        if r['id_numeric_storage']:flags.append('IDENTITY_NUMERIC_STORAGE')
        if len(canonical_oldtokens.get(r['canonical_person_id'],set()))>1:flags.append('CANONICAL_ID_LINK_CHANGE')
        if r['diagnosis_before_onset'] or r['report_before_onset']:flags.append('DATE_SEQUENCE_CONFLICT')
        if r['chronic_diagnosis_flag']:flags.append('CHRONIC_DIAGNOSIS_REVIEW')
        if r['duplicate_flag'] in ('是','1','1.0'):flags.append('SOURCE_DUPLICATE_FLAG')
        if r['duplicate_flag']=='#NUM!':flags.append('SOURCE_DUPLICATE_ERROR')
        if eid in near:flags.append('SAME_PREFIX_WITHIN28_REVIEW')
        if eid in subtype_near:flags.append('CROSS_PREFIX_WITHIN28_REVIEW')
        if r['card_token'] and len(cardgroups[(r['year'],r['card_token'])])>1:flags.append('DUPLICATE_CARD_REVIEW')
        if ann.get('clinical_review_flag')=='code_text_conflict':flags.append('CODE_TEXT_CONFLICT')
        if outcome=='I20_0' and ann.get('clinical_review_flag')!='unstable_text_agrees':flags.append('ACUTE_ANGINA_TEXT_REVIEW')
        if outcome=='I20_0' and r['year']>2023 and eid in near:flags.append('ANGINA_LOCAL_WINDOW_UNCONFIRMED')
        if not r['candidate_present']:decision='outside_existing_candidate_frame';eligible=0;reason='不在既有候选表；保留原始记录审计，未自动恢复或重新定位'
        elif not outcome:decision='excluded';eligible=0;reason='不属于已预设五类编码结局'
        elif 'REVIEW_REJECTED' in flags:decision='excluded';eligible=0;reason='提取时点审核不通过，当前不纳入；如后续修订通过应按新版重新审定'
        elif flags:decision='pending_review';eligible='';reason='待复核：'+';'.join(flags)
        else:decision='included';eligible=1;reason='已终审；身份证格式/校验及人口学一致；预设急性编码和诊断文字无已识别冲突；未发现重卡或短间隔冲突'
        relation='not_classified'
        if eid in subtype_near:relation='cross_subtype_short_interval_pending'
        elif eid in near:relation='duplicate_or_same_monitoring_episode_pending'
        elif r.get('previous_same_prefix_event_id'):relation='new_monitoring_episode_gt28_clinical_recurrence_unconfirmed'
        elif r['canonical_person_id']:relation='first_observed_same_prefix_record_not_lifetime_first'
        x={'event_id':eid,'person_id':r['person_id'],'canonical_person_id':r['canonical_person_id'],'eligible':eligible,'decision':decision,'inclusion_reason':reason,'rules_version':VERSION,'final_outcome':outcome,'dedup_finalized':int(decision in ('included','excluded')),'dedup_rule':'GZ2023_same_person_ICD3_28d_inclusive;2024_2025_reference_only_near_pairs_pending','monitoring_episode_id':r.get('monitoring_episode_id',''),'event_relation':relation,'previous_event_id':r.get('previous_same_prefix_event_id',''),'days_since_previous':r.get('days_since_previous_same_prefix',''),'clinical_recurrence_confirmed':'','review_status':r['review_status'],'source_duplicate_flag':r['duplicate_flag'],'id_check':r['id_check'],'id_dob_conflict':r['id_dob_conflict'],'id_sex_conflict':r['id_sex_conflict'],'id_numeric_storage':r['id_numeric_storage'],'first_onset_flag':r['first_onset_flag'],'review_flags':';'.join(flags),'source_year':r['year'],'source_row':int(eid.split('_')[1]),'candidate_present':r['candidate_present'],'adjudication_basis':'automated_structured_evidence_v1','reviewer':'','review_date':''}
        full.append(x)
        if r['candidate_present']:final.append(x)
    assert len(set(r['event_id'] for r in final))==len(final)
    assert all(r['eligible']=='' and r['dedup_finalized']==0 for r in final if r['decision']=='pending_review')
    assert all(r['eligible']==1 and not r['review_flags'] for r in final if r['decision']=='included')
    save(target,final);save(P/'raw_event_adjudication.csv',full)
    queue=[r for r in final if r['decision']=='pending_review'];save(P/'event_adjudication_review_queue.csv',queue)
    if pairrows:save(P/'event_adjudication_interval_pairs.csv',pairrows)
    for f in [target,P/'raw_event_adjudication.csv',P/'event_adjudication_review_queue.csv',P/'event_adjudication_interval_pairs.csv']:
        if f.exists():os.chmod(f,0o600)
    counts=Counter(r['decision'] for r in final);flags=Counter(f for r in final for f in r['review_flags'].split(';') if f)
    summary={'rules_version':VERSION,'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'raw_records_audited':len(full),'candidate_rows':len(final),'decisions':dict(counts),'review_flags_nonexclusive':dict(flags),'short_interval_pairs_all_raw':len(pairrows),'final_dedup_fully_resolved':counts['pending_review']==0,'formal_model_ready':False,'clinical_recurrence_not_inferred_from_first_flag':True,'candidate_files_unchanged':True,'file_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (O/'adjudication_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    rules={'version':VERSION,'sources':[{'source':'广州2023年官方报告','file':'原始数据/穗疾控办〔2024〕189号广州市疾病预防控制中心关于印发广州市2023年心脑血管事件监测工作报告的通知.docx','rule':'同一人、同一ICD前三位、间隔≤28天为监测重卡','scope':'2023，不能自动外推广州2024—2025全部疾病'},{'url':'https://www.hbcdc.com/wcm.files/upload/CMShbjkzx/202308/202308290118014.pdf','scope':'外地监测参考，非广州本地实施方案'},{'url':'https://www.mashsq.gov.cn/xxgk/openness/detail/content/6948b0a8886688986b8b4579.html','scope':'心梗/卒中28天周期的外地官方参考'}],'decisions':{'included':'在现有候选框架内满足已终审、有效身份证及一致人口学、预设结局且无已识别冲突；属于结构化审定，不是逐份病历专家复核','excluded':'审核不通过或预设结局之外；不删除原始记录','pending_review':'eligible留空，dedup_finalized=0，阻止正式模型；不能当作eligible=0的已确认排除'},'episode_rule':'同人同ICD前三位，固定首日为锚的≤28天监测周期；相邻≤28天的所有端点（含跨锚周期）仍复核以避免链式错误；I21/I22及不同卒中亚型短间隔不自动合并','recurrent_rule':'超过28天仅为不同监测周期；是否临床复发须有病史/新发作证据，首次标记不用于终生首次判定','representative_rule':'同日/同卡号/短间隔冲突均待复核，不自动用首条或已终审优先掩盖地址/诊断冲突','canonical_identity':'15位旧证件转换用于链接核查；发现同一规范化证件对应不同原person_id时进入待复核，不改写既有个人ID','scope_note':'地址精度是另外一道门槛；本表不依据污染浓度、P值或地址定位结果选择事件','overrides':'复核修改应填写reviewer和review_date，并生成新版本保留当前版本和变更记录'}
    (O/'adjudication_rules_v1.json').write_text(json.dumps(rules,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
