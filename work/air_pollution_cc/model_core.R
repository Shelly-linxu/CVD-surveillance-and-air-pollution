# Reusable model and completeness logic; no patient file is loaded here.
suppressPackageStartupMessages(library(data.table));suppressPackageStartupMessages(library(survival))
check_strata<-function(x) {
  z<-x[,.(cases=sum(case),n=.N,dates=uniqueN(date),locations=uniqueN(location_id)),by=event_id]
  if(any(z$cases!=1L|!z$n%in%4:5|z$n!=z$dates|z$locations!=1L))stop('Each fixed stratum must retain one case,3-4 controls,distinct dates,and one residence')
  invisible(TRUE)
}
complete_strata<-function(x,needed) {
  if(!all(needed%in%names(x)))stop('Required model covariates missing')
  ok<-complete.cases(x[,..needed]);keep<-x[,.(ok=all(ok[.I])),by=event_id][ok==TRUE,event_id]
  x[event_id%in%keep]
}
fit_one<-function(x,exposure,temp_cols=paste0('temp_cb',1:9),holiday_col='holiday',interaction=NULL) {
  needed<-c(exposure,temp_cols,paste0('rh_ns',1:3),holiday_col,'adjusted_workday',if(!is.null(interaction))interaction)
  before<-uniqueN(x$event_id);z<-complete_strata(copy(x),needed);check_strata(z)
  vv<-z[,.(varies=uniqueN(get(exposure))>1),by=event_id];coefname<-if(is.null(interaction))'pollution10' else 'pollution10:modifier'
  result<-data.table(n_events=uniqueN(z$event_id),events_lost_missing=before-uniqueN(z$event_id),variable_exposure_events=sum(vv$varies),OR=NA_real_,lower=NA_real_,upper=NA_real_,p=NA_real_,status='insufficient_within_stratum_variation',warnings='')
  if(sum(vv$varies)<20L)return(list(result=result,fit=NULL))
  z[,pollution10:=get(exposure)/10];terms<-c('pollution10',temp_cols,paste0('rh_ns',1:3),holiday_col,'adjusted_workday')
  if(!is.null(interaction)){z[,modifier:=get(interaction)];terms<-c(terms,'pollution10:modifier')}
  form<-as.formula(paste('case ~',paste(terms,collapse=' + '),'+ strata(event_id)'));warn<-character()
  fit<-tryCatch(withCallingHandlers(clogit(form,data=z,method='efron',cluster=person_id,control=coxph.control(iter.max=50)),warning=function(w){warn<<-c(warn,conditionMessage(w));invokeRestart('muffleWarning')}),error=function(e)e)
  if(inherits(fit,'error')){result[,status:='fit_error'];result[,warnings:=conditionMessage(fit)];return(list(result=result,fit=NULL))}
  result[,warnings:=paste(unique(warn),collapse=' | ')];tab<-summary(fit)$coefficients
  if(!coefname%in%rownames(tab)){result[,status:='term_not_estimable'];return(list(result=result,fit=fit))}
  beta<-tab[coefname,'coef'];se<-tab[coefname,'robust se'];pv<-tab[coefname,'Pr(>|z|)']
  if(is.finite(beta)&&is.finite(se)&&se>0&&!any(fit$iter>=50)&&!any(grepl('infinite|converg|iterations',warn,ignore.case=TRUE)))result[,`:=`(OR=exp(beta),lower=exp(beta-1.96*se),upper=exp(beta+1.96*se),p=pv,status='estimated')] else result[,status:='nonconvergence_or_nonfinite']
  list(result=result,fit=fit)
}
month_block_bootstrap<-function(x,exposure,B=200L,seed=20261002L,temp_cols=paste0('temp_cb',1:9)) {
  # Sample entire year-month strata; clone event IDs for repeated block draws.
  x<-copy(x);x[,year:=format(as.Date(date),'%Y')];x[,month:=format(as.Date(date),'%Y-%m')];set.seed(seed);coef<-rep(NA_real_,B)
  for(b in seq_len(B)) {
    pieces<-list();index<-0L
    for(y in unique(x$year)) {
      months<-sort(unique(x[year==y,month]));draws<-sample(months,length(months),replace=TRUE)
      for(m in draws){index<-index+1L;q<-copy(x[month==m]);q[,event_id:=paste0(event_id,'_draw',index)];pieces[[index]]<-q}
    }
    boot<-rbindlist(pieces);fit<-fit_one(boot,exposure,temp_cols);if(fit$result$status=='estimated')coef[b]<-log(fit$result$OR)
  }
  valid<-is.finite(coef);list(successful=sum(valid),requested=B,lower=if(sum(valid)>=.8*B)exp(quantile(coef[valid],.025)) else NA_real_,upper=if(sum(valid)>=.8*B)exp(quantile(coef[valid],.975)) else NA_real_,logOR_draws=coef)
}
