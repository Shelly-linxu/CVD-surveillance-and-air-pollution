# Fixed regional weather bases computed without residence coordinates or outcomes.
suppressPackageStartupMessages(library(data.table));library(splines);library(jsonlite)
root<-normalizePath('.');private<-file.path(root,'work/air_pollution_cc/private');out<-file.path(root,'outputs/air_pollution_cc/parallel_preparation')
w<-as.data.table(read.csv(gzfile(file.path(root,'work/air_pollution_cc/weather_era5/weather_grid_daily.csv.gz'))))
w[,date:=as.IDate(date)];setorder(w,weather_grid_id,date)
stopifnot(nrow(w)==112400L,uniqueN(w$weather_grid_id)==100L,!anyNA(w[,.(temp,rh)]),!anyDuplicated(w[,.(weather_grid_id,date)]),all(w$rh>=0&w$rh<=100))
stopifnot(all(w[,.(ok=all(diff(as.integer(date))==1L)),by=weather_grid_id]$ok))
w[,rh_ma03:=frollmean(rh,4L,align='right',na.rm=FALSE),by=weather_grid_id]
configs<-list(main=list(lag=21L,vdf=3L,ldf=3L),lag14=list(lag=14L,vdf=3L,ldf=3L),lag28=list(lag=28L,vdf=3L,ldf=3L),df4=list(lag=21L,vdf=4L,ldf=4L))
bounds<-range(w$temp);rhbounds<-range(w$rh_ma03,na.rm=TRUE);rhknots<-as.numeric(quantile(w$rh_ma03,c(1/3,2/3),na.rm=TRUE));meta<-list(temperature_bounds=bounds,humidity_bounds=rhbounds,humidity_knots=rhknots,weather_population='100 fixed regional ERA5 grid points,2022-12-04..2025-12-31; no outcome conditioning',configs=list())
basecols<-c('weather_grid_id','date','temp','rh_ma03')
for(name in names(configs)) {
  cfg<-configs[[name]];L<-cfg$lag;vk<-as.numeric(quantile(w$temp,(1:(cfg$vdf-1))/cfg$vdf));lb<-ns(0:L,df=cfg$ldf,intercept=TRUE);cbcols<-paste0('temp_cb',1:(cfg$vdf*cfg$ldf))
  result<-w[,{
    tb<-ns(temp,knots=vk,Boundary.knots=bounds,intercept=FALSE)
    z<-matrix(0,.N,cfg$vdf*cfg$ldf)
    for(lag in 0:L) {
      shifted<-if(lag==0L)tb else rbind(matrix(NA_real_,lag,ncol(tb)),tb[1:(.N-lag),,drop=FALSE])
      for(a in 1:cfg$vdf)for(b in 1:cfg$ldf)z[,(a-1)*cfg$ldf+b]<-z[,(a-1)*cfg$ldf+b]+shifted[,a]*lb[lag+1L,b]
    }
    rhb<-matrix(NA_real_,.N,3L);good<-is.finite(rh_ma03);rhb[good,]<-ns(rh_ma03[good],knots=rhknots,Boundary.knots=rhbounds,intercept=FALSE)
    z<-as.data.table(z);setnames(z,cbcols);rhb<-as.data.table(rhb);setnames(rhb,paste0('rh_ns',1:3));cbind(data.table(date=date,temp=temp,rh_ma03=rh_ma03),z,rhb)
  },by=weather_grid_id]
  result<-result[date>=as.IDate('2023-01-01')];stopifnot(nrow(result)==109600L,!anyNA(result),!anyDuplicated(result[,.(weather_grid_id,date)]))
  file<-file.path(private,paste0('weather_basis_',name,'.csv.gz'));fwrite(result,file,compress='gzip');Sys.chmod(file,'0600')
  meta$configs[[name]]<-list(max_lag=L,temperature_df=cfg$vdf,lag_df=cfg$ldf,temperature_knots=vk,lag_knots=as.numeric(attr(lb,'knots')),lag_bounds=as.numeric(attr(lb,'Boundary.knots')),variable_intercept=FALSE,lag_intercept=TRUE,rows=nrow(result),temperature_columns=cbcols,humidity_columns=paste0('rh_ns',1:3),file=basename(file),missing_values=0)
  cat('Prepared weather basis:',name,nrow(result),'rows\n')
}
write_json(meta,file.path(out,'固定气象样条参数.json'),pretty=TRUE,auto_unbox=TRUE)
writeLines(capture.output(sessionInfo()),file.path(out,'weather_basis_R_sessionInfo.txt'))
