suppressPackageStartupMessages(library(data.table));library(splines);setDTthreads(2)
source('work/air_pollution_cc/model_extensions.R')
out<-'outputs/air_pollution_cc/manuscript';dir.create(file.path(out,'tables'),recursive=TRUE,showWarnings=FALSE)
rr<-list();cc<-list();corr<-list();desc<-list();iq<-NULL
for(family in c('two_group','five_outcomes')){
 s<-readRDS(paste0('work/air_pollution_cc/private/',family,'/registry_model_rows.rds'));x<-s$data;rm(s);stopifnot(!anyNA(x$event_id));check_strata(x)
 w<-fread('work/air_pollution_cc/private/weather_basis_main.csv.gz');w[,date:=as.IDate(date)];x<-merge(x,w[,.(weather_grid_id,date,temp,rh_ma03)],by=c('weather_grid_id','date'),all.x=TRUE)
 groups<-if(family=='two_group')c('CVD','CBVD') else c('MI','ANGINA','IS','ICH','SAH')
 if(family=='two_group'){
  u<-unique(x[,c('location_id','date',paste0(c('PM25','PM10','O3'),'_ma01')),with=FALSE],by=c('location_id','date'))
  iq<-data.table(pollutant=c('PM25','PM10','O3'),IQR=sapply(c('PM25','PM10','O3'),function(p)IQR(u[[paste0(p,'_ma01')]],na.rm=TRUE)),scope='pooled unique residence-date lag01 across two disease groups');fwrite(iq,file.path(out,'tables','supp_IQR_scaling.csv'))
 }
 for(g in groups){z<-x[study_group==g]
  u<-unique(z[,c('location_id','date','PM25_ma01','PM10_ma01','O3_ma01','temp','rh_ma03'),with=FALSE],by=c('location_id','date'))
  if(all(c('PM25_ma01','PM10_ma01','O3_ma01','temp','rh_ma03')%in%names(u))){v<-c('PM25_ma01','PM10_ma01','O3_ma01','temp','rh_ma03');M<-cor(as.matrix(u[,..v]),method='spearman',use='pairwise.complete.obs');d<-as.data.table(as.table(M));setnames(d,c('variable1','variable2','Spearman_r'));d[,outcome_id:=g];corr[[length(corr)+1L]]<-d}
  for(pol in c('PM25','PM10','O3')){
   for(win in c('lag4','lag04')){
    col<-paste0(pol,'_',win);z[,(col):=if(win=='lag4')get(paste0(pol,'_l4')) else rowMeans(.SD,na.rm=FALSE),.SDcols=paste0(pol,'_l',0:4)]
    r<-fit_one(z,col)$result;r[,`:=`(outcome_id=g,pollutant=pol,window=win,scenario='reference_daily_lag_extension',weather_config='main',analysis_status='posthoc_exploratory_registry')];rr[[length(rr)+1L]]<-r
   }
   val<-z[[paste0(pol,'_ma01')]];bounds<-range(val,na.rm=TRUE);kn<-bounds[1]+diff(bounds)*c(1/3,2/3);ref<-median(val,na.rm=TRUE);di<-quantile(val,c(.05,.95),na.rm=TRUE)
   r<-fit_curve(z,paste0(pol,'_ma01'),kn,bounds,ref,seq(di[1],di[2],length.out=80));if(!is.null(r)){r[,`:=`(outcome_id=g,pollutant=pol,scenario='equally_spaced_concentration_knots',analysis_status='posthoc_exploratory_registry')];cc[[length(cc)+1L]]<-r}
   # Fixed tail rule across candidates, removing the whole stratum if any candidate falls outside.
   lohi<-quantile(val,c(.001,.999),na.rm=TRUE);ids<-z[,.(ok=all(is.finite(get(paste0(pol,'_ma01')))&get(paste0(pol,'_ma01'))>=lohi[1]&get(paste0(pol,'_ma01'))<=lohi[2])),by=event_id][ok==TRUE,event_id]
   r<-fit_one(z[event_id%in%ids],paste0(pol,'_ma01'))$result;r[,`:=`(outcome_id=g,pollutant=pol,window='lag01',scenario='trim_candidate_tails_0.1pct_complete_strata',weather_config='main',tail_lower=lohi[1],tail_upper=lohi[2],analysis_status='posthoc_exploratory_registry')];rr[[length(rr)+1L]]<-r
   cat('Reference extension',g,pol,'completed\n');fwrite(rbindlist(rr,fill=TRUE),file.path(out,'tables','supp_reference_extensions.csv'))
  }
 }
 rm(x);gc()
}
fwrite(rbindlist(cc),file.path(out,'tables','supp_equal_knots_curves.csv'));fwrite(rbindlist(corr),file.path(out,'tables','supp_Spearman_correlations.csv'));writeLines(capture.output(sessionInfo()),file.path(out,'R_sessionInfo_reference_extensions.txt'))
