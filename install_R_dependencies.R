packages <- c('data.table', 'survival', 'jsonlite', 'ggplot2', 'gridExtra')
missing <- setdiff(packages, rownames(installed.packages()))
if (length(missing)) install.packages(missing, repos='https://cloud.r-project.org')
sessionInfo()
