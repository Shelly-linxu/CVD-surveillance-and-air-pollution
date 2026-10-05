suppressPackageStartupMessages(library(data.table));library(jsonlite);setDTthreads(2);source('work/air_pollution_cc/model_core.R')
args<-commandArgs(TRUE);scope<-args[1];q<-file.path('work/air_pollution_cc/private',scope);o<-file.path('outputs/air_pollution_cc',scope);x<-readRDS(file.path(q,'registry_model_rows.rds'))$data
x[,age65:=as.integer(age>=65)];x[,male:=fifelse(sex%in%c('男','女'),as.integer(sex=='男'),NA_integer_)];x[,warm:=as.integer(as.integer(format(as.Date(date),'%m'))%in%4:9)]
groups<-if(scope=='two_group')c('CVD','CBVD')else c('MI','ANGINA','IS','ICH','SAH');results<-list();quality<-list();acfout<-list()
for(g in groups)for(pol in c('PM25','PM10','O3')) {
 z<-x[study_group==g];ex<-paste0(pol,'_ma01');needed<-c(ex,paste0('temp_cb',1:9),paste0('rh_ns',1:3),'holiday','adjusted_workday');complete<-complete_strata(z,needed)
 for(mod in c('age65','male','warm')) {
  f<-fit_one(z,ex,interaction=mod);rr<-f$result;zz<-complete_strata(z,c(needed,mod));fitted<-f$fit
  for(level in 0:1) {
   nr<-copy(rr);nr[,`:=`(OR=NA_real_,lower=NA_real_,upper=NA_real_,p=NA_real_)];terms<-c('pollution10','pollution10:modifier')
   if(rr$status=='estimated'){b<-coef(fitted)[terms];v<-vcov(fitted)[terms,terms];a<-c(1,level);eta<-sum(a*b);se<-sqrt(as.numeric(t(a)%*%v%*%a));nr[,`:=`(OR=exp(eta),lower=exp(eta-1.96*se),upper=exp(eta+1.96*se),p=2*pnorm(-abs(eta/se)))]}
   nr[,`:=`(outcome_id=g,pollutant=pol,modifier=mod,level=level,n_events=uniqueN(zz[get(mod)==level,event_id]),interaction_p=rr$p,estimator='interaction_model_contrast_with_shared_weather_adjustment',analysis_status='exploratory')];results[[length(results)+1L]]<-nr
  }
 }
 for(scenario in c('strict_event_core_address','strict_event_core_plus_coarse')) {
  keep<-z$strict_event_approved==1 & if(scenario=='strict_event_core_address')z$sensitivity_core_eligible==1 else z$sensitivity_core_eligible==1|z$sensitivity_coarse_eligible==1
  rr<-fit_one(z[which(keep)],ex)$result;rr[,`:=`(outcome_id=g,pollutant=pol,scenario=scenario,analysis_status='exploratory; core address precision independently unvalidated')];quality[[length(quality)+1L]]<-rr
 }
 f<-fit_one(z,ex)$fit;zz<-copy(complete);zz[,pollution10:=get(ex)/10];terms<-names(coef(f));good<-terms[is.finite(coef(f))];lp<-as.vector(as.matrix(zz[,..good])%*%coef(f)[good]);zz[,lp:=lp];zz[,prob:=exp(lp-max(lp))/sum(exp(lp-max(lp))),by=event_id]
 daily<-zz[,.(residual=sum(case-prob)),by=date];setorder(daily,date);a<-as.numeric(acf(daily$residual,lag.max=21,plot=FALSE)$acf)[-1]
 acfout[[length(acfout)+1L]]<-data.table(outcome_id=g,pollutant=pol,lag=1:21,ACF=a,interpretation='daily aggregated conditional-probability residual; descriptive, calendar-matching constraints induce dependence')
 cat('Completed subgroup/joint-quality/residual checks',scope,g,pol,'\n')
}
fwrite(rbindlist(results),file.path(o,'亚组分层OR与交互P值.csv'),bom=TRUE);fwrite(rbindlist(quality),file.path(o,'严格事件与地址联合限制.csv'),bom=TRUE);fwrite(rbindlist(acfout),file.path(o,'日级残余相关性描述.csv'),bom=TRUE)
