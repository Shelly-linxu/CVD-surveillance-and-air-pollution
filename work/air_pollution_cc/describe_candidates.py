from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[2];P=R/'work/air_pollution_cc/private/two_group';O=R/'outputs/air_pollution_cc/two_group'
a=pd.read_csv(P/'event_adjudication.csv',low_memory=False);a['year']=pd.to_numeric(a['year'])
rows=[]
for group,label in [('CVD','心血管疾病'),('CBVD','脑血管疾病')]:
 z=a[a.study_group==group];row={'疾病':label}
 for year in [2023,2024,2025]:row['年'+str(year)]=int((z.year==year).sum())
 rows.append(row)
pd.DataFrame(rows).to_csv(O/'表1_两类疾病候选事件特征.csv',index=False,encoding='utf-8-sig')
