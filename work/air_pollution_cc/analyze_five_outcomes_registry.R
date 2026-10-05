# Full registry estimates, with all eligibility/coordinate limitations retained.
suppressPackageStartupMessages(library(data.table));library(jsonlite);setDTthreads(2)
root<-normalizePath('.');p<-file.path(root,'work/air_pollution_cc/private');q<-file.path(p,'five_outcomes');o<-file.path(root,'outputs/air_pollution_cc/five_outcomes')
source(file.path(root,'work/air_pollution_cc/model_core.R'))
ad<-fread(file.path(q,'event_adjudication.csv'));stopifnot(nrow(ad)>0,!anyDuplicated(ad$event_id))
m<-readRDS(file.path(p,'two_group/registry_model_rows.rds'))$data;m<-m[event_id%in%ad$event_id];m[,study_group:=NULL];m<-merge(m,ad[,.(event_id,study_group)],by='event_id',all.x=TRUE,sort=FALSE)
m[,(grep('^(temp_cb|rh_ns)',names(m),value=TRUE)):=NULL];check_strata(m)
ad[,cluster_id:=fifelse(!is.na(canonical_person_id)&canonical_person_id!='',canonical_person_id,person_id)]
windows<-c(lag01='ma01',lag0='l0',lag1='l1',lag2='l2',lag3='l3',lag02='ma02',lag03='ma03',lag12='ma12')
a<-copy(ad);a[,onset_date:=as.IDate(onset)];setorder(a,cluster_id,study_group,onset_date,event_id)
first_ids<-a[,.(event_id=event_id[1]),by=.(cluster_id,study_group)]$event_id
# Explicit anchored 28-day scenario: same canonical person and same ICD3.
# Not a confirmed Guangzhou 2024-2025 rule and never writes back adjudication.
setorder(a,cluster_id,icd_prefix,onset_date,event_id)
anchor_ids<-a[,{
 keep<-logical(.N);anchor<-NA_integer_
 for(i in seq_len(.N)){d<-as.integer(onset_date[i]);if(is.na(anchor)||d-anchor>28L){keep[i]<-TRUE;anchor<-d}}
 .(event_id=event_id[keep])
},by=.(cluster_id,icd_prefix)]$event_id
flags<-fread(file.path(root,'outputs/air_pollution_cc/parallel_preparation/监测异常筛查日期清单.csv'))
flag_dates<-as.character(unique(flags[population=='既有候选事件（未新增去重）'&grepl('发病日期计数',flag),date]))
saveRDS(list(first_ids=first_ids,anchor_ids=anchor_ids,onset_screen_flag_dates=flag_dates),file.path(q,'event_sensitivity_selection.rds'));Sys.chmod(file.path(q,'event_sensitivity_selection.rds'),'0600')
results<-list();flow<-list()
append_result<-function(r,group,poll,win,config,scenario) {
 r[,`:=`(outcome_id=group,pollutant=poll,window=win,weather_config=config,scenario=scenario,increment_ug_m3=10,analysis_status='provisional_registry_estimate_not_formal_adjudicated_main')];results[[length(results)+1L]]<<-r
}
for(config in c('main','lag14','lag28','df4')) {
 weather<-as.data.table(read.csv(gzfile(file.path(p,paste0('weather_basis_',config,'.csv.gz')))));weather[,date:=as.IDate(date)];tempcols<-grep('^temp_cb',names(weather),value=TRUE)
 x<-merge(m,weather[,c('weather_grid_id','date',tempcols,paste0('rh_ns',1:3)),with=FALSE],by=c('weather_grid_id','date'),all.x=TRUE,sort=FALSE)
 if(config=='main') {
  # New two-group extension parameters fixed before this run's associations.
  params<-lapply(c('PM25','PM10','O3'),function(pol){v<-x[[paste0(pol,'_ma01')]];list(pollutant=pol,knots=as.numeric(quantile(v,c(1/3,2/3),na.rm=TRUE)),bounds=range(v,na.rm=TRUE),reference=median(v,na.rm=TRUE),display=as.numeric(quantile(v,c(.05,.95),na.rm=TRUE)))})
  write_json(params,file.path(o,'扩展污染样条固定参数.json'),pretty=TRUE,auto_unbox=TRUE)
  saveRDS(list(data=x,scope='reported_registry_exploratory',formal_gate_verified=FALSE,protocol_md5=unname(tools::md5sum(file.path(o,'五类补充分析方案_v1.json')))),file.path(q,'registry_model_rows.rds'));Sys.chmod(file.path(q,'registry_model_rows.rds'),'0600')
 }
 for(group in c('MI','ANGINA','IS','ICH','SAH')) {
  z<-x[study_group==group]
  for(poll in c('PM25','PM10','O3'))for(win in if(config=='main')names(windows) else 'lag01') {
   append_result(fit_one(z,paste0(poll,'_',windows[[win]]),tempcols)$result,group,poll,win,config,'all_registry_all_coordinates')
  }
  if(config!='main')next
  selectors<-list(no_imputed_coordinates=z$coordinate_imputed==0,
   core_addresses=z$sensitivity_core_eligible==1,
   core_plus_coarse_addresses=z$sensitivity_core_eligible==1|z$sensitivity_coarse_eligible==1,
   final_review_only=z$review_status=='已终审',
   strict_previous_adjudication=z$strict_event_approved==1,
   identity_consistent=!grepl('IDENTITY_|CANONICAL_ID_LINK_CHANGE',fifelse(is.na(z$review_flags),'',z$review_flags)),
   no_duplicate_interval_flags=!grepl('SOURCE_DUPLICATE_|SAME_PREFIX_WITHIN28|CROSS_PREFIX_WITHIN28|DUPLICATE_CARD',fifelse(is.na(z$review_flags),'',z$review_flags)),
   first_person_group_record=z$event_id%in%first_ids,
   anchored28_ICD3_scenario=z$event_id%in%anchor_ids,
   acute_code_restriction=if(group%in%c('MI','ANGINA'))z$icd_prefix%in%c('I21','I22')|startsWith(z$icd10,'I20.0') else z$icd_prefix%in%c('I60','I61','I63'),
   exclude_flagged_onset_dates=!z$onset%in%flag_dates)
  flow[[length(flow)+1L]]<-data.table(outcome_id=group,scenario='all_registry_all_coordinates',candidate_events=uniqueN(z$event_id))
  for(name in names(selectors)) {
   zz<-z[which(selectors[[name]])];flow[[length(flow)+1L]]<-data.table(outcome_id=group,scenario=name,candidate_events=uniqueN(zz$event_id))
   for(poll in c('PM25','PM10','O3'))append_result(fit_one(zz,paste0(poll,'_ma01'),tempcols)$result,group,poll,'lag01',config,name)
  }
  for(poll in c('PM25','PM10','O3')) {
   common<-complete_strata(z,c(paste0(poll,'_',windows),tempcols,paste0('rh_ns',1:3),'holiday','adjusted_workday'))
   for(win in names(windows))append_result(fit_one(common,paste0(poll,'_',windows[[win]]),tempcols)$result,group,poll,win,config,'all_windows_common_complete')
   append_result(fit_one(z,paste0(poll,'_ma01'),tempcols,holiday_col='official_break')$result,group,poll,'lag01',config,'official_break_calendar')
  }
  cat('Completed main and event/address sensitivity:',group,'\n')
  fwrite(rbindlist(results),file.path(o,'五类疾病关联与敏感性_运行中.csv'),bom=TRUE)
 }
 cat('Completed weather config',config,'\n')
}
r<-rbindlist(results);r[,q:=NA_real_]
ii<-which(r$scenario=='all_registry_all_coordinates'&r$weather_config=='main'&r$window=='lag01'&is.finite(r$p));r$q[ii]<-p.adjust(r$p[ii],method='BH',n=15L)
r[,q_family:='exploratory_five_outcomes_x_three_pollutants_lag01_15_tests'];fwrite(r,file.path(o,'五类疾病关联与敏感性.csv'),bom=TRUE);fwrite(rbindlist(flow),file.path(o,'敏感性样本流程.csv'),bom=TRUE)
write_json(list(attempted_models=nrow(r),estimated_models=sum(r$status=='estimated'),formal_main_models=0,registry_analyses_include_unadjudicated_records=TRUE,registry_analyses_include_imputed_coordinates=TRUE),file.path(o,'模型运行核验.json'),pretty=TRUE,auto_unbox=TRUE)
writeLines(capture.output(sessionInfo()),file.path(o,'five_outcomes_R_sessionInfo.txt'));cat('Two-group registry and sensitivity analyses saved\n')
