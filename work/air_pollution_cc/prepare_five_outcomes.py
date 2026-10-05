"""Create local subtype inputs without overriding event adjudication."""
from pathlib import Path
import csv,json,os
ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'work/air_pollution_cc/private';Q=P/'five_outcomes';O=ROOT/'outputs/air_pollution_cc/five_outcomes'
def main():
 Q.mkdir(parents=True,exist_ok=True);O.mkdir(parents=True,exist_ok=True)
 with (P/'two_group/event_adjudication.csv').open(encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
 mapping={'I21':'MI','I22':'MI','I20':'ANGINA','I63':'IS','I61':'ICH','I60':'SAH'}
 selected=[]
 for row in rows:
  prefix=row['icd_prefix']
  if prefix in mapping: selected.append(dict(row,study_group=mapping[prefix]))
 if not selected: raise ValueError('No mapped subtype events')
 target=Q/'event_adjudication.csv'
 if target.exists(): raise FileExistsError('Preserve existing adjudication; use a new version directory')
 with target.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(selected[0]));w.writeheader();w.writerows(selected)
 os.chmod(target,0o600)
 (O/'五类补充分析方案_v1.json').write_text(json.dumps({'scope':'exploratory_registry_subtypes','mapping':mapping,'angina_acute_eligibility':'requires_verification','main_window':'lag01','FDR_family_size':15},indent=2))
if __name__=='__main__': main()
