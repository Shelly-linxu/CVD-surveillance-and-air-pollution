suppressPackageStartupMessages(library(data.table)); source('work/air_pollution_cc/model_core_fast.R');setDTthreads(2)
o<-'outputs/air_pollution_cc/manuscript_season_revision';dir.create(file.path(o,'tables'),recursive=TRUE,showWarnings=FALSE)
b<-'outputs/air_pollution_cc/manuscript_reviewed_bw/tables'
i<-rbindlist(list(fread(file.path(b,'S29_two_group_interactions.csv')),fread(file.path(b,'S30_subtype_interactions.csv'))))[modifier=='warm'];i[,q_season21:=p.adjust(p,'BH')];fwrite(i,file.path(o,'tables','Season_interaction_all21.csv'))
target<-i[p<.05];out<-list();checks<-list()
for(scope in c('two_group','five_outcomes')){
 x<-readRDS(file.path('work/air_pollution_cc/private',scope,'registry_model_rows.rds'))$data
 x[,warm:=as.integer(as.integer(format(as.Date(date),'%m'))%in%4:9)]
 ids<-if(scope=='two_group')c('CVD','CBVD')else c('MI','ANGINA','IS','ICH','SAH')
 for(k in seq_len(nrow(target[outcome_id%in%ids]))){t<-target[outcome_id%in%ids][k];z<-x[study_group==t$outcome_id];ex<-paste0(t$pollutant,'_ma01');f<-fit_one(z,ex,interaction='warm');stopifnot(f$result$status=='estimated',abs(f$result$p-t$p)<1e-6)
  need<-c(ex,paste0('temp_cb',1:9),paste0('rh_ns',1:3),'holiday','adjusted_workday','warm');zz<-complete_strata(z,need);stopifnot(zz[,all(uniqueN(warm)==1),by=event_id]$V1)
  for(s in 0:1){a<-c(1,s);terms<-c('pollution10','pollution10:modifier');be<-sum(a*coef(f$fit)[terms]);se<-sqrt(as.numeric(t(a)%*%vcov(f$fit)[terms,terms]%*%a));rr<-data.table(outcome_id=t$outcome_id,pollutant=t$pollutant,season=if(s==1)'Warm (April-September)'else 'Cold (October-March)',estimator='interaction_model_shared_weather',n_events=uniqueN(zz[warm==s,event_id]),OR=exp(be),lower=exp(be-1.96*se),upper=exp(be+1.96*se),p=2*pnorm(-abs(be/se)),interaction_p=t$p,interaction_q21=t$q_season21,status='estimated');out[[length(out)+1]]<-rr
   sf<-fit_one(z[warm==s],ex)$result;sf[,`:=`(outcome_id=t$outcome_id,pollutant=t$pollutant,season=rr$season,estimator='separately_fitted_season_specific_weather',interaction_p=t$p,interaction_q21=t$q_season21)];out[[length(out)+1]]<-sf
  };cat('Completed',t$outcome_id,t$pollutant,'\n')
 }
}
r<-rbindlist(out,fill=TRUE);stopifnot(all(r$status=='estimated'));fwrite(r,file.path(o,'tables','Season_followup_significant_pairs.csv'));cat('All',nrow(r),'seasonal estimates completed\n')
