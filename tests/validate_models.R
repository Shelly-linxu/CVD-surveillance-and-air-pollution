# Entirely synthetic validation. Output is not a Guangzhou disease result.
source('work/air_pollution_cc/model_core.R');library(jsonlite);set.seed(20261002)
N<-1800L;k<-4L;beta<-.18
x<-data.table(event_id=rep(paste0('S',1:N),each=k),person_id=rep(paste0('P',(1:N-1L)%%600+1L),each=k),location_id=rep(paste0('L',1:N),each=k),date=rep(as.IDate(c('2024-06-03','2024-06-10','2024-06-17','2024-06-24')),N),case=0L,PM25_ma01=runif(N*k,5,90),holiday=0L,adjusted_workday=0L)
for(v in c(paste0('temp_cb',1:9),paste0('rh_ns',1:3)))x[,(v):=0]
for(i in 1:N){ii<-((i-1)*k+1):(i*k);chosen<-sample(ii,1,prob=exp(beta*x$PM25_ma01[ii]/10));x$case[chosen]<-1L}
check_strata(x);result<-fit_one(x,'PM25_ma01');stopifnot(result$result$status=='estimated',abs(log(result$result$OR)-beta)<.05)
# Independent one-case conditional likelihood via grouped softmax.
xx<-matrix(x$PM25_ma01/10,nrow=N,byrow=TRUE);cc<-matrix(x$case,nrow=N,byrow=TRUE)
nll<-function(b){v<-b*xx;mx<-apply(v,1,max);-sum(v*cc)+sum(mx+log(rowSums(exp(v-mx))))}
manual<-optimize(nll,c(-1,1),tol=1e-10)$minimum;stopifnot(abs(manual-log(result$result$OR))<1e-6)
exact<-clogit(case~I(PM25_ma01/10)+strata(event_id),data=x,method='exact');stopifnot(abs(coef(exact)[1]-log(result$result$OR))<1e-7)
bad<-copy(x);bad[1,PM25_ma01:=NA_real_];reduced<-complete_strata(bad,'PM25_ma01');stopifnot(uniqueN(reduced$event_id)==N-1,!('S1'%in%reduced$event_id),nrow(reduced)==(N-1)*k)
cat('Synthetic conditional-likelihood, exact/efron and missing-stratum checks passed\n')
