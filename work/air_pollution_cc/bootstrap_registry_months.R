# Integer block frequencies equal cloned one-case strata likelihood up to constants.
suppressPackageStartupMessages(library(data.table));library(survival);library(jsonlite);setDTthreads(2)
source('work/air_pollution_cc/model_core.R')
args<-commandArgs(TRUE);scope<-if(length(args))args[1] else 'two_group';B<-200L
p<-'work/air_pollution_cc/private';q<-file.path(p,scope);o<-file.path('outputs/air_pollution_cc',scope)
saved<-readRDS(file.path(q,'registry_model_rows.rds'));stopifnot(!saved$formal_gate_verified);x<-saved$data;rm(saved)
groups<-if(scope=='two_group')c('CVD','CBVD')else c('MI','ANGINA','IS','ICH','SAH');out<-list();set.seed(20261003)
summary_path<-file.path(o,'整月时间块重抽样.csv');previous<-if(file.exists(summary_path))fread(summary_path)else data.table()
# Common reproducible year-stratified block draws across outcomes/pollutants.
months<-sort(unique(format(as.Date(x$date),'%Y-%m')));draws<-replicate(B,{freq<-setNames(integer(length(months)),months);for(y in unique(substr(months,1,4))){mm<-months[substr(months,1,4)==y];freq[mm]<-tabulate(match(sample(mm,length(mm),replace=TRUE),mm),length(mm))};freq})
for(g in groups)for(pol in c('PM25','PM10','O3')) {
 if(nrow(previous)&&nrow(previous[outcome_id==g&pollutant==pol&requested_draws==B])){out[[length(out)+1L]]<-previous[outcome_id==g&pollutant==pol];next}
 z<-complete_strata(x[study_group==g],c(paste0(pol,'_ma01'),paste0('temp_cb',1:9),paste0('rh_ns',1:3),'holiday','adjusted_workday'));check_strata(z)
 z[,pollution10:=get(paste0(pol,'_ma01'))/10];z[,month:=format(as.Date(date),'%Y-%m')];stopifnot(all(z[,.(ok=uniqueN(month)==1L),by=event_id]$ok))
 terms<-c('pollution10',paste0('temp_cb',1:9),paste0('rh_ns',1:3),'holiday','adjusted_workday');form<-as.formula(paste('Surv(rep(1,.N),case)~',paste(terms,collapse='+'),'+strata(event_id)'))
 # coxph formula does not evaluate .N in data.frame environment; fixed time column.
 z[,time:=1];form<-as.formula(paste('Surv(time,case)~',paste(terms,collapse='+'),'+strata(event_id)'))
 z<-z[,c('event_id','case','time','month',terms),with=FALSE]
 base<-coxph(form,data=z,ties='breslow',control=coxph.control(iter.max=50));logor<-rep(NA_real_,B);messages<-character(B)
 # Validate integer weights vs explicit duplicated strata on first 300 events.
 small<-z[event_id%in%unique(z$event_id)[seq_len(min(300L,uniqueN(z$event_id)))]];small[,bw:=1L+as.integer(as.integer(factor(event_id))%%2L==0L)]
 weighted<-coxph(form,data=small,weights=bw,ties='breslow');copies<-rbindlist(list(small,small[bw==2L]));copies[(nrow(small)+1L):.N,event_id:=paste0(event_id,'_copy')]
 cloned<-coxph(form,data=copies,ties='efron');delta<-abs(coef(weighted)['pollution10']-coef(cloned)['pollution10']);stopifnot(is.finite(delta),delta<1e-6)
 xx<-as.matrix(z[,..terms]);yy<-Surv(z$time,z$case);ss<-as.integer(factor(z$event_id));mi<-match(z$month,months);backend_delta<-NA_real_
 checkpoint<-file.path(q,paste0(g,'_',pol,'_month_draws.csv'));done<-0L
 if(file.exists(checkpoint)){old<-fread(checkpoint);stopifnot(nrow(old)<=B,identical(old$draw,seq_len(nrow(old))));done<-nrow(old);logor[seq_len(done)]<-old$logOR;messages[seq_len(done)]<-old$warning}
 if(done<B)for(b in (done+1L):B) {
  ww<-as.integer(draws[mi,b]);ii<-which(ww>0L);warn<-character()
  f<-tryCatch(withCallingHandlers(coxph.fit(xx[ii,,drop=FALSE],yy[ii,,drop=FALSE],ss[ii],offset=rep(0,length(ii)),init=coef(base),control=coxph.control(iter.max=50),weights=ww[ii],method='breslow',rownames=NULL,resid=FALSE),warning=function(w){warn<<-c(warn,conditionMessage(w));invokeRestart('muffleWarning')}),error=function(e)e)
  if(b==done+1L&&!inherits(f,'error')){zz<-copy(z[ii]);zz[,bw:=ww[ii]];check<-coxph(form,data=zz,weights=bw,ties='breslow',init=coef(base));backend_delta<-max(abs(coef(check)-f$coefficients),na.rm=TRUE);stopifnot(is.finite(backend_delta),backend_delta<1e-6)}
  if(!inherits(f,'error')&&!any(f$iter>=50L)&&!any(grepl('infinite|converg|iterations',warn,ignore.case=TRUE))&&is.finite(f$coefficients['pollution10']))logor[b]<-f$coefficients['pollution10']
  messages[b]<-if(inherits(f,'error'))conditionMessage(f)else paste(unique(warn),collapse=' | ')
  if(b%%10L==0L){fwrite(data.table(draw=seq_len(b),logOR=logor[seq_len(b)],warning=messages[seq_len(b)]),checkpoint);Sys.chmod(checkpoint,'0600');cat(scope,g,pol,b,'/',B,'matrix engine','\n')}
 }
 valid<-is.finite(logor);ci<-if(sum(valid)>=.8*B)exp(quantile(logor[valid],c(.025,.975)))else c(NA_real_,NA_real_)
 out[[length(out)+1L]]<-data.table(outcome_id=g,pollutant=pol,n_events=uniqueN(z$event_id),OR=exp(coef(base)['pollution10']),lower_month_block=ci[1],upper_month_block=ci[2],requested_draws=B,successful_draws=sum(valid),clone_validation_abs_beta_difference=delta,matrix_engine_abs_beta_difference=backend_delta,analysis_status='exploratory_registry_month_bootstrap')
 fwrite(rbindlist(out,fill=TRUE),file.path(o,'整月时间块重抽样.csv'),bom=TRUE)
}
write_json(list(B=B,seed=20261003,blocks=length(months),year_stratified=TRUE,all_fixed_case_control_strata_preserved=TRUE,integer_weight_clone_equivalence_verified=TRUE,matrix_backend_vs_formula_verified=TRUE,resumed_existing_draws_without_changes=TRUE,Monte_Carlo_tail_uncertainty=TRUE),file.path(o,'整月重抽样方法核验.json'),pretty=TRUE,auto_unbox=TRUE)
