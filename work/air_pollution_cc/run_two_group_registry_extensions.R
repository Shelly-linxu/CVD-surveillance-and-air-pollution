suppressPackageStartupMessages(library(data.table));library(jsonlite)
source('work/air_pollution_cc/model_extensions.R')
q<-'work/air_pollution_cc/private/two_group';o<-'outputs/air_pollution_cc/two_group'
saved<-readRDS(file.path(q,'registry_model_rows.rds'));stopifnot(identical(saved$scope,'reported_registry_exploratory'),identical(saved$formal_gate_verified,FALSE))
x<-saved$data;rm(saved);check_strata(x)
x[,age65:=as.integer(age>=65)];x[,male:=fifelse(sex%in%c('男','女'),as.integer(sex=='男'),NA_integer_)];x[,warm:=as.integer(as.integer(format(as.Date(date),'%m'))%in%4:9)]
params<-read_json(file.path(o,'扩展污染样条固定参数.json'),simplifyVector=FALSE)
r2<-list();ri<-list();rc<-list();rl<-list();rcl<-list();rt<-list()
for(g in c('CVD','CBVD')) {
 z<-x[study_group==g]
 for(pair in list(c('PM25','O3'),c('PM10','O3'))) {
  r<-fit_two_pollutant(z,paste0(pair[1],'_ma01'),paste0(pair[2],'_ma01'));r[,`:=`(outcome_id=g,first=pair[1],second=pair[2])];r2[[length(r2)+1L]]<-r
 }
 for(pol in c('PM25','PM10','O3')) {
  for(mod in c('age65','male','warm')) {
   r<-fit_one(z,paste0(pol,'_ma01'),interaction=mod)$result;r[,`:=`(outcome_id=g,pollutant=pol,modifier=mod,contrast='ratio_of_ORs')];ri[[length(ri)+1L]]<-r
  }
  pa<-params[[match(pol,vapply(params,function(a)a$pollutant,''))]]
  cur<-fit_curve(z,paste0(pol,'_ma01'),unlist(pa$knots),unlist(pa$bounds),pa$reference,seq(pa$display[[1]],pa$display[[2]],length.out=80))
  if(is.null(cur))cur<-data.table(status='not_estimable') else cur[,status:='estimated'];cur[,`:=`(outcome_id=g,pollutant=pol)];rc[[length(rc)+1L]]<-cur
  lag<-fit_pollution_lag(z,pol)
  if(is.null(lag)){ll<-data.table(status='not_estimable');cc<-copy(ll)}else{ll<-lag$lag;cc<-lag$cumulative;ll[,status:='estimated'];cc[,status:='estimated']}
  ll[,`:=`(outcome_id=g,pollutant=pol)];cc[,`:=`(outcome_id=g,pollutant=pol)];rl[[length(rl)+1L]]<-ll;rcl[[length(rcl)+1L]]<-cc
  # Alternative covariance clustered on complete calendar months. Only 36 clusters;
  # use t(35), explicitly not a bootstrap or a two-way cluster estimator.
  zz<-copy(z);zz[,person_id:=format(as.Date(date),'%Y-%m')]
  fitted<-fit_one(zz,paste0(pol,'_ma01'));r<-fitted$result
  if(r$status=='estimated'){tab<-summary(fitted$fit)$coefficients['pollution10',];b<-tab['coef'];s<-tab['robust se'];df<-uniqueN(zz$person_id)-1L;r[,`:=`(lower=exp(b-qt(.975,df)*s),upper=exp(b+qt(.975,df)*s),p=2*pt(-abs(b/s),df),cluster_count=df+1L)]}
  r[,`:=`(outcome_id=g,pollutant=pol,covariance='calendar_month_cluster_t; not bootstrap; not two_way_cluster')];rt[[length(rt)+1L]]<-r
  cat('Completed extensions',g,pol,'\n')
 }
}
for(a in list(list(r2,'双污染物模型.csv'),list(ri,'亚组交互作用.csv'),list(rc,'暴露反应曲线.csv'),list(rl,'分布滞后逐日.csv'),list(rcl,'分布滞后累积.csv'),list(rt,'月份聚类标准误敏感性.csv'))) {
 r<-rbindlist(a[[1]],fill=TRUE);r[,analysis_status:='exploratory_registry_not_formal_main'];fwrite(r,file.path(o,a[[2]]),bom=TRUE)
}
cat('Registry extensions finished\n')
