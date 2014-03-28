"""The features module generates a feature matrix each row is a gene
and features are specified in different columns. The generate_feature_matrix
function specifies how the feature matrix is constructed.
"""
from utils.python.amino_acid import AminoAcid
import recurrent_mutation as recur
import plot_data
import pandas.io.sql as psql
import utils.python.util as _utils
from collections import OrderedDict
import shutil
import csv
import logging

logger = logging.getLogger(__name__)

def generate_feature_matrix(recurrency_threshold,
                            conn,
                            recurrency_cap=float('inf')):
    """Generate a feature matrix potentially useful for classifying genes.

    **Parameters**

    recurrency_threshold : int
        minimum number of mutations to define recurrency
    conn : db connection
        database connection to mysql/sqlite
    recurrency_cap : int
        maximum number of mutations to define recurrency

    **Returns**

    features : list
        feature matrix
    """
    logger.info('Creating design matrix . . .')

    # query database
    df = psql.frame_query("SELECT * FROM cosmic_mutation", con=conn)  # get all
    mtypes = _utils.get_mutation_types(df['AminoAcid'],
                                       df['Nucleotide'])
    df['mut_types'] = mtypes  # add mutation types to SQL output
    gene_to_indexes = df.groupby('Gene').groups

    # aggregate info
    design_matrix = []
    not_used_types = ['not valid',
                      'missing',
                      'unknown effect']  # only include known mutations
    for gene, indexes in gene_to_indexes.iteritems():
        tmp_df = df.ix[indexes]
        gene_pos_counter = {}
        identical_indel = {}
        mut_type_ctr = OrderedDict([['missense', 0],
                                    ['frame shift', 0],
                                    ['synonymous', 0],
                                    #['not valid', 0],
                                    ['inframe indel', 0],
                                    ['no protein', 0],
                                    ['lost stop', 0],
                                    ['splicing mutation', 0],
                                    #['missing', 0],
                                    ['nonsense', 0]])
                                    #['unknown effect', 0]])
        # count identical indels
        for i, hgvs in enumerate(tmp_df['AminoAcid']):
            aa = AminoAcid(hgvs)
            if aa.mutation_type not in not_used_types:
                # do not use 'missing', 'unkown effect' or 'not valid'
                # if aa.mutation_type == 'missense':
                    # keep track of missense pos for recurrency
                #    gene_pos_counter.setdefault(aa.pos, 0)
                #    gene_pos_counter[aa.pos] += 1
                if aa.mutation_type == 'inframe indel' and tmp_df['mut_types'].iloc[i] != 'splicing mutation':
                    # keep track of missense pos for recurrency
                    identical_indel.setdefault(aa.hgvs_original, 0)
                    identical_indel[aa.hgvs_original] += 1

        # count mutation types
        for mt in tmp_df['mut_types']:
            if mt not in not_used_types:
                mut_type_ctr[mt] += 1

        recur_ct, missense_ct = recur.count_missense_types(tmp_df['AminoAcid'],
                                                           recurrency_threshold,
                                                           recurrency_cap)

        # needs to have at least one count
        if sum(mut_type_ctr.values()):
            mut_type_ctr['missense'] = missense_ct
            #recurrent_cts = sum([cts for cts in gene_pos_counter.values()
            #                     if cts >= recurrency_threshold])
            identical_cts = sum([cts for cts in identical_indel.values()
                                 if cts >= recurrency_threshold])
            #mut_type_ctr['missense'] -= recurrent_cts  # subtract off the recurrent missense
            mut_type_ctr['inframe indel'] -= identical_cts  # subtract off the recurrent missense
            design_matrix.append([gene, recur_ct, identical_cts] + list(mut_type_ctr.values()))
    header = [['gene', 'recurrent missense', 'recurrent indel'] + list(mut_type_ctr)]
    logger.info('Finished creating feature matrix.')
    return header + design_matrix


def main(recurrent, recurrent_max, conn):
    cfg_opts = _utils.get_output_config('feature_matrix')  # get config

    # generate features
    feature_matrix = generate_feature_matrix(recurrent, conn,
                                             recurrency_cap=recurrent_max)

    # save features
    feature_path = _utils.result_dir + cfg_opts['gene_feature_matrix']
    with open(feature_path, 'wb') as handle:
        csv.writer(handle, delimiter='\t').writerows(feature_matrix)
    copy_path = feature_path.strip('txt') + 'r%d.txt' % recurrent
    shutil.copy(feature_path, copy_path)  # record a second file with reccurent param in name

    # PCA plots
    # unnormalized PCA plot
    plot_data.pca_plot(_utils.result_dir + cfg_opts['gene_feature_matrix'],
                       _utils.plot_dir + cfg_opts['pca_plot'],
                       title='Protein Mutation Type Composition PCA')
    # normalized PCA by removing class imbalance
    plot_data.pca_plot(_utils.result_dir + cfg_opts['gene_feature_matrix'],
                       _utils.plot_dir + cfg_opts['pca_plot_rand'],
                       norm_class=True,
                       low_count_filter=10,
                       title='Protein Mutation Type Composition PCA Subsampled by '
                       'Gene Type (3:1)')

