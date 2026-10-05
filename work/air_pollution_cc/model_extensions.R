# Prespecified secondary/exploratory helpers; caller must pass final approved rows.
source('work/air_pollution_cc/model_core.R');library(splines)
fit_custom<-function(x,design,terms) {
  z<-copy(x);for(n in names(design))z[,(n):=design[[n]]]
  adj<-c(paste0('temp_cb',1:9),paste0('rh_ns',1:3),'holiday','adjusted_workday');z<-complete_strata(z,c(terms,adj));check_strata(z)
  if(uniqueN(z$event_id)<20L)return(NULL)
  formula<-as.formula(paste('case~',paste(c(terms,adj),collapse='+'),'+strata(event_id)'))
  fit<-tryCatch(clogit(formula,data=z,method='efron',cluster=person_id,control=coxph.control(iter.max=50)),error=function(e)NULL)
  if(is.null(fit)||any(fit$iter>=50L)||any(!is.finite(coef(fit)[terms])))return(NULL)
  fit
}
contrasts<-function(fit,terms,B) {
  coef<-coef(fit)[terms];V<-vcov(fit)[terms,terms,drop=FALSE];eta<-as.vector(B%*%coef);se<-sqrt(pmax(0,rowSums((B%*%V)*B)))
  data.table(OR=exp(eta),lower=exp(eta-1.96*se),upper=exp(eta+1.96*se))
}
fit_two_pollutant<-function(x,first,second) {
  names<-c('poll_first','poll_second');fit<-fit_custom(x,list(poll_first=x[[first]]/10,poll_second=x[[second]]/10),names)
  if(is.null(fit))return(data.table(status='not_estimable'))
  table<-summary(fit)$coefficients[names,,drop=FALSE];data.table(term=names,OR=exp(table[,'coef']),lower=exp(table[,'coef']-1.96*table[,'robust se']),upper=exp(table[,'coef']+1.96*table[,'robust se']),p=table[,'Pr(>|z|)'],status='estimated')
}
fit_curve<-function(x,exposure,knots,bounds,reference,grid) {
  good<-is.finite(x[[exposure]]);B<-matrix(NA_real_,nrow(x),3);B[good,]<-ns(x[[exposure]][good],knots=knots,Boundary.knots=bounds,intercept=FALSE)
  terms<-paste0('poll_ns',1:3);design<-as.list(as.data.frame(B));names(design)<-terms;fit<-fit_custom(x,design,terms)
  if(is.null(fit))return(NULL)
  curves<-ns(grid,knots=knots,Boundary.knots=bounds,intercept=FALSE);ref<-as.numeric(ns(reference,knots=knots,Boundary.knots=bounds,intercept=FALSE));delta<-sweep(curves,2,ref,'-')
  cbind(data.table(concentration=grid,reference=reference),contrasts(fit,terms,delta))
}
fit_pollution_lag<-function(x,pollutant,L=7L) {
  lagbasis<-ns(0:L,df=3,intercept=TRUE);hist<-as.matrix(x[,paste0(pollutant,'_l',0:L),with=FALSE])/10;B<-hist%*%lagbasis;terms<-paste0('poll_lag_cb',1:3);design<-as.list(as.data.frame(B));names(design)<-terms;fit<-fit_custom(x,design,terms)
  if(is.null(fit))return(NULL)
  perlag<-cbind(data.table(lag=0:L),contrasts(fit,terms,lagbasis));cumulative<-contrasts(fit,terms,matrix(colSums(lagbasis),nrow=1));cumulative[,contrast:='each of lag0-7 raised by10ug/m3; distributed-lag cumulative OR']
  list(lag=perlag,cumulative=cumulative)
}
