"""Stream public CHAP archives and preserve raw values in a buffered rectangle.
Rectangle is a processing extent, not a Guangzhou administrative boundary.
Original coordinates and packing are preserved; this is not person exposure.
"""
from pathlib import Path
import ctypes as C, ctypes.util, csv, json, re, zipfile, argparse
from datetime import date, timedelta
import netCDF4, numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/air_pollution_cc'
DEST=ROOT/'work/air_pollution_cc/chap_guangzhou_buffer'
BBOX=(112.7,22.3,114.5,24.4)  # west, south, east, north; includes a buffer

def rar_members(path):
    lib=C.CDLL(ctypes.util.find_library('archive'))
    for name, restype, args in [
        ('archive_read_new',C.c_void_p,[]),
        ('archive_read_support_filter_all',C.c_int,[C.c_void_p]),
        ('archive_read_support_format_all',C.c_int,[C.c_void_p]),
        ('archive_read_open_filename',C.c_int,[C.c_void_p,C.c_char_p,C.c_size_t]),
        ('archive_read_next_header',C.c_int,[C.c_void_p,C.POINTER(C.c_void_p)]),
        ('archive_entry_pathname',C.c_char_p,[C.c_void_p]),
        ('archive_entry_size',C.c_longlong,[C.c_void_p]),
        ('archive_read_data',C.c_longlong,[C.c_void_p,C.c_void_p,C.c_size_t]),
        ('archive_read_data_skip',C.c_int,[C.c_void_p]),
        ('archive_read_free',C.c_int,[C.c_void_p]),
        ('archive_error_string',C.c_char_p,[C.c_void_p])]:
        f=getattr(lib,name); f.restype=restype; f.argtypes=args
    ar=lib.archive_read_new(); lib.archive_read_support_filter_all(ar); lib.archive_read_support_format_all(ar)
    try:
        if lib.archive_read_open_filename(ar,str(path).encode(),1024*1024)!=0: raise RuntimeError('Archive open failed')
        entry=C.c_void_p()
        while True:
            status=lib.archive_read_next_header(ar,C.byref(entry))
            if status==1: break
            if status<0: raise RuntimeError((lib.archive_error_string(ar) or b'Archive read failed').decode())
            name=lib.archive_entry_pathname(entry).decode()
            size=lib.archive_entry_size(entry)
            if not name.lower().endswith('.nc'): lib.archive_read_data_skip(ar); continue
            if not 0<size<256*1024*1024: raise RuntimeError('Unexpected NetCDF member size')
            buf=C.create_string_buffer(size); offset=0
            while offset<size:
                n=lib.archive_read_data(ar,C.byref(buf,offset),size-offset)
                if n<=0: raise RuntimeError('Incomplete archive member')
                offset+=n
            yield name,buf.raw
    finally: lib.archive_read_free(ar)

def members(path):
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith('.nc'): yield name,z.read(name)
    else: yield from rar_members(path)

def crop(blob,target,row,original_name):
    with netCDF4.Dataset('memory.nc',memory=blob) as ds:
        lat=np.asarray(ds.variables['lat'][:]); lon=np.asarray(ds.variables['lon'][:])
        if lat.ndim!=1 or lon.ndim!=1: raise ValueError('Expected rectilinear geographic axes')
        iy=np.where((lat>=BBOX[1])&(lat<=BBOX[3]))[0]; ix=np.where((lon>=BBOX[0])&(lon<=BBOX[2]))[0]
        if not len(iy) or not len(ix): raise ValueError('Processing rectangle not covered')
        if not np.all(np.diff(iy)==1) or not np.all(np.diff(ix)==1): raise ValueError('Noncontiguous coordinates')
        vars=[v for v in ds.variables.values() if v.dimensions==('lat','lon')]
        if len(vars)!=1: raise ValueError('Expected one pollutant field')
        src=vars[0]; src.set_auto_maskandscale(False)
        raw=np.asarray(src[iy[0]:iy[-1]+1,ix[0]:ix[-1]+1])
        fill=getattr(src,'_FillValue',None); valid=np.ones(raw.shape,dtype=bool) if fill is None else raw!=fill
        scale=float(getattr(src,'scale_factor',1)); offset=float(getattr(src,'add_offset',0))
        if src.dtype!=np.dtype('uint16') or fill!=65535 or not np.isclose(scale,.1): raise ValueError('Product packing changed; review required')
        tmp=target.with_suffix('.partial.nc')
        with netCDF4.Dataset(tmp,'w',format='NETCDF4') as dst:
            dst.setncatts({a:ds.getncattr(a) for a in ds.ncattrs()})
            dst.source_archive=row['filename']; dst.source_record=row['record']; dst.source_member=original_name
            dst.processing_extent=json.dumps(BBOX); dst.processing_note='Buffered rectangle; not administrative boundary or person exposure.'
            dst.source_lat_index=int(iy[0]); dst.source_lon_index=int(ix[0])
            for name,values in [('lat',lat[iy]),('lon',lon[ix])]:
                sv=ds.variables[name]; dst.createDimension(name,len(values)); dv=dst.createVariable(name,sv.dtype,(name,))
                dv.setncatts({a:sv.getncattr(a) for a in sv.ncattrs() if a!='_FillValue'}); dv[:]=values
            dv=dst.createVariable(src.name,src.dtype,('lat','lon'),fill_value=fill,zlib=True,complevel=4)
            dv.setncatts({a:src.getncattr(a) for a in src.ncattrs() if a!='_FillValue'})
            dv.set_auto_maskandscale(False); dv[:]=raw
        tmp.replace(target)
        # Exact raw-value round trip; the later reader auto-decodes scale and mask.
        with netCDF4.Dataset(target) as verify:
            check=verify.variables[src.name]; check.set_auto_maskandscale(False)
            if not np.array_equal(check[:],raw): raise ValueError('Crop round trip changed concentrations')
        vals=raw[valid].astype(float)*scale+offset
        return dict(variable=src.name,lat_cells=len(iy),lon_cells=len(ix),valid_cells=int(valid.sum()),missing_cells=int((~valid).sum()),min_ug_m3=float(vals.min()) if vals.size else None,max_ug_m3=float(vals.max()) if vals.size else None,scale_factor=scale,fill_value=int(fill),units=str(getattr(src,'units','')),source_lon_step=float(np.median(np.abs(np.diff(lon)))),source_lat_step=float(np.median(np.abs(np.diff(lat)))))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=0); args=ap.parse_args()
    manifest=list(csv.DictReader((OUT/'chap_download_manifest.csv').open(encoding='utf-8-sig')))
    statusfile=OUT/'chap_crop_status.json'; inventory=OUT/'chap_crop_inventory.jsonl'
    done=0; counts={}
    DEST.mkdir(parents=True,exist_ok=True)
    for row in manifest:
        p=Path(row['local_file']);year=int(re.search(r'_D1K_(\d{4})_',p.name)[1]); folder=DEST/row['pollutant']/str(year);folder.mkdir(parents=True,exist_ok=True)
        seen=set()
        for name,blob in members(p):
            stamp=re.search(r'(?<!\d)('+str(year)+r'\d{4})(?!\d)',Path(name).name)[1]
            d=date(int(stamp[:4]),int(stamp[4:6]),int(stamp[6:])); assert d not in seen;seen.add(d)
            target=folder/Path(name).name
            if not target.exists():
                info=crop(blob,target,row,name)
                with inventory.open('a',encoding='utf-8') as log:log.write(json.dumps(dict(pollutant=row['pollutant'],date=d.isoformat(),path=str(target),**info),ensure_ascii=False)+'\n')
            done+=1; counts[row['pollutant']+'_'+str(year)]=len(seen)
            if done%30==0 or done==1:
                statusfile.write_text(json.dumps(dict(daily_files_processed=done,counts=counts,bbox=BBOX,scope='buffered_rectangle_only',association_models=0),indent=2))
                print(json.dumps(dict(daily_files_processed=done,pollutant=row['pollutant'],year=year)),flush=True)
            if args.limit and done>=args.limit: return
        expected=366 if year==2024 else 365
        if len(seen)!=expected: raise ValueError('Incomplete daily coverage')
    statusfile.write_text(json.dumps(dict(daily_files_processed=done,counts=counts,bbox=BBOX,scope='buffered_rectangle_only',complete=True,association_models=0),indent=2))
    print('Complete:',done,flush=True)

if __name__=='__main__':main()
