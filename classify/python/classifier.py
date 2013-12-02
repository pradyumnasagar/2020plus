from __future__ import division
import matplotlib.pyplot as plt
from vogelstein_classifier import VogelsteinClassifier
from random_forest_clf import RandomForest
from multinomial_nb_clf import MultinomialNaiveBayes
from dummy_clf import DummyClf
import utils.python.util as _utils
import plot_data
import pandas as pd
import numpy as np
import glob
import re


def calc_onco_info(df, onco_pct, tsg_pct, min_ct):
    # calculate the number of genes classified as oncogene
    vclf = VogelsteinClassifier(onco_pct, tsg_pct, min_ct)
    df['total'] = df.T.sum()
    input_list = ((row['recurrent missense'] + row['recurrent indel'],
                   row['frame shift'] + row['nonsense'] + row['lost stop'] + row['no protein'],
                   row['total'])
                  for i, row in df.iterrows())
    df['2020 class'] = vclf.predict_list(input_list)
    class_cts = df['2020 class'].value_counts()

    # calculate the pct of known oncogenes found
    df['curated class'] = [_utils.classify_gene(gene)
                           for gene in df.index.tolist()]
    tmpdf = df.copy()  # prevent wierd behavior
    known_onco = tmpdf[tmpdf['curated class']=='oncogene']
    num_onco_found = len(known_onco[known_onco['2020 class']=='oncogene'])
    total_onco = len(known_onco)  # total number of oncogenes with counts
    pct_onco_found = num_onco_found / total_onco

    return class_cts['oncogene'], pct_onco_found


def num_onco_by_recurrent_mutations(onco_pct, tsg_pct, min_ct):
    """Count number of oncogenes while varying the definition of recurrency"""
    # calculate counts for oncogenes/tsg with varying the required the number
    # of mutations to define a recurrent position
    file_match_pattern = './data_analysis/results/genes/gene_feature_matrix.r*.txt'
    gene_design_matrix_paths = glob.glob(file_match_pattern)
    onco_ct_list, onco_pct_list = [], []  # list of cts/pct for oncogenes
    for file_path in gene_design_matrix_paths:
        tmp_df = pd.read_csv(file_path, sep='\t', index_col=0)
        tmp_ct, tmp_pct = calc_onco_info(tmp_df,
                                         onco_pct=onco_pct,  # pct thresh for onco
                                         tsg_pct=tsg_pct,  # pct thresh for tsg
                                         min_ct=min_ct)  # min count for a gene
        onco_ct_list.append(tmp_ct)
        onco_pct_list.append(tmp_pct)

    # extract the '-r' parameter from the file name
    recur_param_pattern = '\d+'
    recur_param_list = [int(re.search(recur_param_pattern, mypath).group())
                        for mypath in gene_design_matrix_paths]

    # return dataframe with counts for each use of a recurrent mutation counts
    mycts = pd.Series(onco_ct_list, index=recur_param_list)
    mypct = pd.Series(onco_pct_list, index=recur_param_list)
    return mycts, mypct


def num_onco_by_pct_threshold(min_ct):
    # initialization of dataframe
    cts, pct = num_onco_by_recurrent_mutations(.2, .2, min_ct)
    df_ct = pd.DataFrame(index=cts.index)
    df_pct = pd.DataFrame(index=pct.index)

    # test different percentage thresholds
    for threshold in np.arange(.15, .5, .05):
        tmp_ct, tmp_pct = num_onco_by_recurrent_mutations(threshold, threshold, min_ct)
        df_ct[str(threshold)] = tmp_ct
        df_pct[str(threshold)] = tmp_pct
    return df_ct, df_pct


def main(minimum_ct):
    cfg_opts = _utils.get_output_config('classifier')

    # get oncogene info
    count_df, pct_df = num_onco_by_pct_threshold(minimum_ct)
    count_df = count_df.sort_index()  # sort df by recurrent mutation cts
    pct_df = pct_df.sort_index()  # sort df by recurrent mutation cts

    # save results
    count_df.to_csv(_utils.clf_result_dir + cfg_opts['oncogene_parameters_ct'], sep='\t')
    pct_df.to_csv(_utils.clf_result_dir + cfg_opts['oncogene_parameters_pct'], sep='\t')

    # plot results
    # plot number of predicted oncogenes while varying parameters
    tmp_save_path = _utils.clf_plot_dir + cfg_opts['number_oncogenes_plot']
    tmp_title = r"Vogelstein's Classifier Predicted Oncogenes (recurrent missense \textgreater 10)"
    tmp_ylabel = 'Number of Oncogenes'
    tmp_xlabel = 'Number of Mutations Required for Recurrency'
    plot_data.onco_mutations_parameter(count_df,
                                       tmp_save_path,
                                       title=tmp_title,
                                       ylabel=tmp_ylabel,
                                       xlabel=tmp_xlabel)
    # plot percentage of vogelstein's oncogenes recovered
    tmp_title = 'Percentage of Vogelstein\'s Oncogenes Recovered'
    tmp_ylabel = 'Fraction of Oncogenes'
    tmp_xlabel = 'Number of Mutations Required for Recurrency'
    tmp_save_path = _utils.clf_plot_dir + cfg_opts['pct_oncogenes_plot']
    plot_data.onco_mutations_parameter(pct_df,
                                       tmp_save_path,
                                       title=tmp_title,
                                       ylabel=tmp_ylabel,
                                       xlabel=tmp_xlabel)

    df = pd.read_csv(_utils.result_dir + cfg_opts['gene_feature'],
                     sep='\t', index_col=0)

    # random forest
    print 'Random forest'
    rclf = RandomForest(df, min_ct=minimum_ct)
    rclf.kfold_validation()
    rclf_mean_tpr, rclf_mean_fpr, rclf_mean_roc_auc = rclf.get_roc_metrics()
    rclf_mean_precision, rclf_mean_recall, rclf_mean_pr_auc = rclf.get_pr_metrics()
    mean_df = rclf.mean_importance
    std_df = rclf.std_importance
    plot_data.feature_importance_barplot(mean_df,
                                         std_df,
                                         _utils.clf_plot_dir + cfg_opts['feature_importance_plot'])

    # multinomial naive bayes
    print 'naive bayes'
    nbclf = MultinomialNaiveBayes(df, min_ct=minimum_ct)
    nbclf.kfold_validation()
    nbclf_mean_tpr, nbclf_mean_fpr, nbclf_mean_roc_auc = nbclf.get_roc_metrics()
    nbclf_mean_precision, nbclf_mean_recall, nbclf_mean_pr_auc = nbclf.get_pr_metrics()

    # dummy classifier, predict most frequent
    print 'dummy'
    dclf = DummyClf(df, strategy='most_frequent', min_ct=minimum_ct)
    dclf.kfold_validation()
    dclf_mean_tpr, dclf_mean_fpr, dclf_mean_roc_auc = dclf.get_roc_metrics()
    dclf_mean_precision, dclf_mean_recall, dclf_mean_pr_auc = dclf.get_pr_metrics()

    # plot roc figure
    df = pd.DataFrame({'random forest (AUC = %0.3f)' % rclf_mean_roc_auc: rclf_mean_tpr,
                       'naive bayes (AUC = %0.3f)' % nbclf_mean_roc_auc: nbclf_mean_tpr,
                       'dummy (AUC = %0.3f)' % dclf_mean_roc_auc: dclf_mean_tpr},
                      index=rclf_mean_fpr)
    save_path = _utils.clf_plot_dir + cfg_opts['roc_plot']
    plot_data.receiver_operator_curve(df, save_path)

    # plot pr figure
    df = pd.DataFrame({'random forest (AUC = %0.3f)' % rclf_mean_pr_auc: rclf_mean_precision,
                       'naive bayes (AUC = %0.3f)' % nbclf_mean_pr_auc: nbclf_mean_precision,
                       'dummy (AUC = %0.3f)' % dclf_mean_pr_auc: dclf_mean_precision},
                      index=rclf_mean_recall)
    save_path = _utils.clf_plot_dir + 'pr.png'
    plot_data.precision_recall_curve(df, save_path)


if __name__ == "__main__":
    main()
