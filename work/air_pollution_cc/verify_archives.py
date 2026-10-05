"""Validate downloaded public CHAP archives and inventory daily files without extraction."""
from pathlib import Path
import csv, hashlib, json, re, subprocess, zipfile
from datetime import date, timedelta
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/air_pollution_cc'

def main():
    with (OUT/'chap_download_manifest.csv').open(encoding='utf-8-sig') as f: manifest=list(csv.DictReader(f))
    inventory=[]
    for row in manifest:
        p=Path(row['local_file']); yr=int(re.search(r'_D1K_(\d{4})_',p.name)[1])
        result={'pollutant':row['pollutant'],'year':yr,'filename':p.name,'expected_bytes':int(row['bytes']),'download_state':'not_complete','checksum':'not_checked','daily_nc_files':None,'calendar_coverage':'not_checked'}
        if not p.exists(): inventory.append(result); continue
        h=hashlib.md5()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
        result['checksum']='pass' if 'md5:'+h.hexdigest()==row['checksum'] else 'fail'
        result['download_state']='complete' if p.stat().st_size==int(row['bytes']) and result['checksum']=='pass' else 'invalid'
        if result['download_state']!='complete': inventory.append(result); continue
        if p.suffix=='.zip':
            with zipfile.ZipFile(p) as z: names=z.namelist()
        else:
            r=subprocess.run(['/usr/bin/tar','-tf',str(p)],capture_output=True,text=True)
            if r.returncode:
                result['calendar_coverage']='archive_listing_failed: '+r.stderr[:200]; inventory.append(result); continue
            names=r.stdout.splitlines()
        ncs=[n for n in names if n.lower().endswith('.nc')]
        dates=[]
        for n in ncs:
            match=re.search(r'(?<!\d)('+str(yr)+r'\d{4})(?!\d)',Path(n).name)
            if match:
                s=match[1]
                try: dates.append(date(int(s[:4]),int(s[4:6]),int(s[6:])))
                except ValueError: pass
        expected=set(); d=date(yr,1,1)
        while d.year==yr: expected.add(d); d+=timedelta(days=1)
        result['daily_nc_files']=len(ncs)
        result['calendar_coverage']='pass' if set(dates)==expected and len(dates)==len(expected) else 'needs_review_filename_dates'
        result['expected_days']=len(expected)
        inventory.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    fields=['pollutant','year','filename','expected_bytes','download_state','checksum','daily_nc_files','calendar_coverage','expected_days']
    with (OUT/'chap_archive_validation.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(inventory)
    print(json.dumps({'complete_archives':sum(r['download_state']=='complete' for r in inventory),'total_archives':len(inventory),'calendar_passed':sum(r['calendar_coverage']=='pass' for r in inventory)}))

if __name__=='__main__': main()
