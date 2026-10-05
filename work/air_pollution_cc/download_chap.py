"""Pinned public CHAP downloads. Never sends any case data. Resume and validate MD5."""
from pathlib import Path
import csv, json, hashlib, subprocess, argparse, threading, time
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/air_pollution_cc'; DATA=ROOT/'work/air_pollution_cc/chap_archives'
RECORDS={'PM25':21770406,'PM10':21773535,'O3':21811088}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--metadata-only',action='store_true'); ap.add_argument('--max-seconds',type=int,default=0); ap.add_argument('--workers',type=int,default=3); args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True); DATA.mkdir(parents=True,exist_ok=True); rows=[]
    for pollutant,record in RECORDS.items():
        meta=DATA/f'{record}.json'
        if not meta.exists():
            subprocess.run(['curl','-sS','-L','--fail','--max-time','30',f'https://zenodo.org/api/records/{record}','-o',str(meta)],check=True)
        obj=json.loads(meta.read_text())
        for file in obj['files']:
            name=file['key']
            if '_D1K_' in name and any(f'_{y}_' in name for y in range(2022,2026)):
                rows.append({'pollutant':pollutant,'record':record,'filename':name,'bytes':file['size'],'checksum':file['checksum'],'url':file['links']['self'],'local_file':str(DATA/name)})
    with (OUT/'chap_download_manifest.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(json.dumps({'files':len(rows),'total_GB':sum(r['bytes'] for r in rows)/1e9},ensure_ascii=False),flush=True)
    if args.metadata_only: return
    rows.sort(key=lambda r:(r['pollutant'],r['filename']))
    lock=threading.Lock(); statuses={r['filename']:{'state':'pending','bytes':0,'total':r['bytes']} for r in rows}
    def snapshot():
        for name,s in statuses.items():
            target=DATA/name; part=DATA/(name+'.part')
            s['bytes']=target.stat().st_size if target.exists() else part.stat().st_size if part.exists() else 0
        tmp=OUT/'download_status.json.tmp'
        tmp.write_text(json.dumps({'verified_complete_archives':sum(s['state']=='verified' for s in statuses.values()),'files':statuses},indent=2))
        tmp.replace(OUT/'download_status.json')
    def update(r,state,n):
        with lock:
            statuses[r['filename']]={'state':state,'bytes':n,'total':r['bytes']}
            snapshot()
    stopped=threading.Event()
    def monitor():
        while not stopped.wait(10):
            with lock: snapshot()
    def digest(path):
        h=hashlib.md5()
        with path.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
        return 'md5:'+h.hexdigest()
    def download(r):
        target=Path(r['local_file']); part=target.with_suffix(target.suffix+'.part')
        if target.exists():
            if digest(target)==r['checksum']:
                update(r,'verified',target.stat().st_size); return True
            raise RuntimeError('Existing archive failed checksum: '+target.name)
        print('Downloading '+r['filename'],flush=True)
        # Do not automatically retry a timed-out transfer: curl may truncate the
        # current attempt. A fresh invocation resumes from the retained offset.
        stalled=0
        while True:
            before=part.stat().st_size if part.exists() else 0
            update(r,'downloading',before)
            rc=subprocess.run(['curl','-sS','-L','--fail','--connect-timeout','30','--speed-time','60','--speed-limit','1024','--max-time',str(args.max_seconds),'-C','-','-o',str(part),r['url']]).returncode
            after=part.stat().st_size if part.exists() else 0
            update(r,'downloading' if rc else 'checking_md5',after)
            if rc==0 or after==r['bytes']: break
            stalled=stalled+1 if after<=before else 0
            if rc not in (6,7,18,28,35,52,56) or stalled>=3:
                update(r,'incomplete_curl_'+str(rc),after)
                print('Incomplete '+r['filename']+' curl='+str(rc),flush=True); return False
            print('Resume '+r['filename']+' '+str(after)+'/'+str(r['bytes']),flush=True)
            time.sleep(min(2**stalled,10))
        if part.stat().st_size!=r['bytes'] or digest(part)!=r['checksum']:
            update(r,'checksum_failed',part.stat().st_size); return False
        part.replace(target)
        print('Validated '+target.name,flush=True)
        update(r,'verified',target.stat().st_size); return True
    threading.Thread(target=monitor,daemon=True).start()
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,6))) as pool:
        results=list(pool.map(download,rows))
    stopped.set()
    with lock: snapshot()
    if not all(results): raise SystemExit(1)
    print('All 12 archives downloaded and MD5 verified.',flush=True)

if __name__=='__main__': main()
