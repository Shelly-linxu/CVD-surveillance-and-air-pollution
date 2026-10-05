suppressPackageStartupMessages({library(data.table);library(ggplot2);library(splines);library(gridExtra)})
O<-'outputs/air_pollution_cc/manuscript_figure_revision'
l<-fread('outputs/air_pollution_cc/two_group/分布滞后逐日.csv')
dense<-l[,{
 B<-ns(lag,df=3,intercept=TRUE); beta<-qr.solve(B,log(OR)); se<-(log(upper)-log(lower))/(2*1.96)
 X<-cbind(B[,1]^2,B[,2]^2,B[,3]^2,2*B[,1]*B[,2],2*B[,1]*B[,3],2*B[,2]*B[,3]);v<-qr.solve(X,se^2)
 V<-matrix(c(v[1],v[4],v[5],v[4],v[2],v[6],v[5],v[6],v[3]),3)
 stopifnot(max(abs(as.vector(B%*%beta)-log(OR)))<1e-10,max(abs(X%*%v-se^2))<1e-10)
 xx<-seq(0,7,length.out=281);BB<-predict(B,xx);eta<-as.vector(BB%*%beta);ss<-sqrt(pmax(0,rowSums((BB%*%V)*BB)))
 data.table(lag=xx,OR=exp(eta),lower=exp(eta-1.96*ss),upper=exp(eta+1.96*ss))
},by=.(outcome_id,pollutant)]
fwrite(dense,file.path(O,'Figure2_dense_lag_predictions.csv'))
G<-c(CVD='Cardiovascular',CBVD='Cerebrovascular');P<-c(PM25='PM2.5',PM10='PM10',O3='O3')
prep<-function(d){d[,outcome:=factor(G[outcome_id],levels=G)];d[,pol:=factor(P[pollutant],levels=P)];d}
dense<-prep(dense);cur<-prep(fread('outputs/air_pollution_cc/two_group/暴露反应曲线.csv'))
theme_set(theme_bw(base_size=16)+theme(panel.grid.minor=element_blank(),strip.background=element_rect(fill='#F2F2F2'),axis.text=element_text(size=12),strip.text=element_text(size=13),plot.tag=element_text(face='bold',size=18)))
a<-ggplot(dense,aes(lag,OR))+geom_hline(yintercept=1,linetype=2,color='grey50')+geom_ribbon(aes(ymin=lower,ymax=upper),fill='#D9D9D9')+geom_line(color='black')+facet_grid(outcome~pol,scales='free_y')+scale_x_continuous(breaks=c(0,2,4,7))+labs(x='Lag (days)',y='Lag-specific OR per 10 ug/m3 (95% CI)',tag='A')
b<-ggplot(cur,aes(concentration,OR))+geom_hline(yintercept=1,linetype=2,color='grey50')+geom_ribbon(aes(ymin=lower,ymax=upper),fill='#D9D9D9')+geom_line(color='black')+facet_grid(outcome~pol,scales='free')+labs(x='Lag 0-1 concentration (ug/m3)',y='OR relative to reference concentration (95% CI)',tag='B')
g<-arrangeGrob(a,b,ncol=1)
ggsave(file.path(O,'Figure2_lag_and_exposure_response.png'),g,width=9,height=11,dpi=300)
ggsave(file.path(O,'Figure2_lag_and_exposure_response.pdf'),g,width=9,height=11,device=pdf)
