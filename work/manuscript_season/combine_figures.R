suppressPackageStartupMessages(library(gridExtra));library(grid)
plots<-list();code<-readLines('work/manuscript_review/plot_black_white.R');code[grep('^O<-',code)]<-"O<-'outputs/air_pollution_cc/manuscript_season_revision';dir.create(file.path(O,'figures'),recursive=TRUE,showWarnings=FALSE)"
code[grep('^saveplot<-',code)]<-"saveplot<-function(p,n,w=9,h=6){plots[[n]]<<-p}"
# Data inputs remain the verified aggregate tables.
code<-gsub("file.path(O,'tables'","file.path('outputs/air_pollution_cc/manuscript_reviewed_bw','tables'",code,fixed=TRUE)
eval(parse(text=code));plots$Figure1_candidate_flow<-plots$Figure1_candidate_flow+theme(axis.text=element_blank(),axis.title=element_blank(),axis.ticks=element_blank(),panel.grid=element_blank()); for(n in c('Figure5_two_pollutant','Figure6a_quality_sensitivity','Figure6b_quality_sensitivity')) plots[[n]]<-plots[[n]]+scale_x_continuous(breaks=function(x)pretty(x,n=2));for(n in c('Figure6a_quality_sensitivity','Figure6b_quality_sensitivity')) plots[[n]]<-plots[[n]]+scale_x_continuous(breaks=c(.98,1,1.02,1.04),labels=function(x)formatC(x,format='f',digits=2));o<-'outputs/air_pollution_cc/manuscript_season_revision/figures'
label<-function(p,t){p+labs(tag=t)+theme(text=element_text(size=16),plot.tag=element_text(face='bold',size=18),axis.text=element_text(size=12),strip.text=element_text(size=13),legend.text=element_text(size=13))}
s<-fread('outputs/air_pollution_cc/manuscript_season_revision/tables/Season_followup_significant_pairs.csv')[estimator=='interaction_model_shared_weather'];s[,association:=factor(paste(G[outcome_id],P[pollutant],sep=': '),levels=rev(unique(paste(G[outcome_id],P[pollutant],sep=': '))))]
sp<-ggplot(s,aes(OR,association,shape=season))+geom_vline(xintercept=1,linetype=2,color='grey50')+geom_errorbar(aes(xmin=lower,xmax=upper),orientation='y',position=position_dodge(.55),width=.15)+geom_point(position=position_dodge(.55),size=3)+scale_shape_manual(values=c(16,1))+labs(x='OR per 10 ug/m3 increase (95% CI)',y=NULL,shape=NULL)
combine<-function(name,a,b,heights=c(1,1),h=11){aa<-label(a,'A');if(name=='Figure1_study_population_and_associations')aa<-aa+theme(axis.text=element_blank(),axis.title=element_blank(),axis.ticks=element_blank(),panel.grid=element_blank());g<-arrangeGrob(aa,label(b,'B'),ncol=1,heights=heights);ggsave(file.path(o,paste0(name,'.png')),g,width=9,height=h,dpi=300);ggsave(file.path(o,paste0(name,'.pdf')),g,width=9,height=h,device=pdf)}
combine('Figure1_study_population_and_associations',plots$Figure1_candidate_flow,plots$Figure2_main_forest,c(.95,1),11)
combine('Figure2_lag_and_exposure_response',plots$Figure3_distributed_lag,plots$Figure4_exposure_response,c(1,1),11)
combine('Figure3_season_and_copollutant',sp,plots$Figure5_two_pollutant,c(.8,1.2),11)
combine('Figure4_sensitivity_analyses',plots$Figure6a_quality_sensitivity,plots$Figure6b_quality_sensitivity,c(1,1),10)
cat('Four combined vector/Png figures generated\n')
