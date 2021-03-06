#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Purpose
-------
For each assembler, this script will output to the command line for each reference genome:
  * Contiguity - largest % of reference covered by a single contig
  * lowest identity - % of identity to the reference of the worst mapping contig
  * breadth of coverage - % of the reference genome covered by the contigs
  * aligned contigs - number of aligned contigs to the reference
  * aligned basepairs - total number of basepairs aligned to te reference

The following custom metrics are implemented:
  * C90 - Number of contigs, ordered by length, that cover 90% of the reference genome
  * NID - Normalized identity by contig lenght


Expected input
--------------
This script takes the following arguments (in this order):
  * Path to the metagenomic assembly files (ending in *.fasta)
  * Path to the mapped contigs to the triple reference genomes (ending in *.paf)

The triple bacterial reference files for the zymos mock community are available at
"../../data/references/Zymos_Genomes_triple_chromosomes.fasta"

Authorship
----------
Inês Mendes, cimendes@medicina.ulisboa.pt
https://github.com/cimendes

Part of this work was adapted from
https://raw.githubusercontent.com/rrwick/Long-read-assembler-comparison/master/scripts/assembly_stats.py
"""

import sys
from itertools import groupby
import glob
import os
import re
import fnmatch
import math
import pandas as pd
from plotly import subplots
from plotly.offline import plot
import plotly.graph_objects as go

#import commonly used functions from utils.py
import utils

REFERENCE_SEQUENCES = os.path.join(os.path.dirname(__file__),
                                   '..', '..', 'data', 'references', 'Zymos_Genomes_triple_chromosomes.fasta')

# colors for each subplot
colours = ['#a6cee3', '#1f78b4', '#b2df8a', '#33a02c', '#fb9a99', '#e31a1c',
           '#fdbf6f', '#ff7f00', '#cab2d6', '#6a3d9a', '#ffff99', '#b15928']


def get_phred_quality_score(identity):
    """
    Using the formula -log10(1-identity)*10, receives the identity of a contig and outputs the corresponding phred
    quality score.
    If the identity is 1, a Phred score of 60 (error rate of 0.0001%) is returned
    :param identity: float with identity values for the contig
    :return: float with phred score for contig identity
    """
    return - math.log10(1-identity) * 10 if identity < 1 else 60


def get_c90(alignment_lengths, ref_len):
    """
    Returns the number of contigs, ordered by length, that cover at least 90% of the reference sequence.
    :param alignment_lengths: list with length of mapped contigs for the reference
    :param ref_len: int with the expected reference length
    :return: int with the number of contigs that represent
    """
    sorted_lengths = sorted(alignment_lengths, reverse=True)  # from longest to shortest
    target_length = ref_len * 0.9

    length_so_far = 0
    c90 = 0
    for contig_length in sorted_lengths:
        length_so_far += contig_length
        if length_so_far >= target_length:
            c90 += 1
    return c90


def get_c95(alignment_lengths, ref_len):
    """
    Returns the number of contigs, ordered by length, that cover at least 95% of the reference sequence.
    :param alignment_lengths: list with length of mapped contigs for the reference
    :param ref_len: int with the expected reference length
    :return: int with the number of contigs that represent
    """
    sorted_lengths = sorted(alignment_lengths, reverse=True)  # from longest to shortest
    target_length = ref_len * 0.95

    length_so_far = 0
    c95 = 0
    for contig_length in sorted_lengths:
        length_so_far += contig_length
        if length_so_far >= target_length:
            c95 += 1
    return c95


def get_covered_bases(covered_bases_list, ref_len):
    """
    Get ration of referee lengths (adjusted for triple reference) covered by mapping contigs
    :param covered_bases_list: list with alignment coordinates
    :param ref_len: expected reference length
    :return: % of reference covered by the alignment
    """
    sorted_list = sorted(covered_bases_list, key=lambda x: x[0])

    covered_bases = set()

    for item in sorted_list:
        start, stop = map(int, item[:])

        # Due to the triple reference, the values need to be adjusted as not to over-estimate coverage breadth.
        # Therefore, the coordinates are adjusted as follows:
        # [0; ref_len][ref_len+1; 2*ref_len][(2*ref_len)+1; 3*ref_len]
        for base in range(start, stop):
            if base <= ref_len:
                covered_bases.add(base)
            elif base <= 2*ref_len:
                covered_bases.add(base-ref_len)
            else:
                covered_bases.add(base-(2*ref_len))
    return len(covered_bases)/ref_len


def get_expanded_cigar(cigar):
    """

    :param cigar: string with cigar values
    :return: string with expanded cigar values for alignment
    """
    expanded_cigar = []
    cigar_parts = re.findall(r'\d+[IDX=]', cigar)
    for cigar_part in cigar_parts:
        num = int(cigar_part[:-1])
        letter = cigar_part[-1]
        expanded_cigar.append(letter * num)
    return ''.join(expanded_cigar)


def get_lowest_window_identity(cigar, window_size):
    """

    :param cigar: string with alignment cigar
    :param window_size: int with window size
    :return: float with lowest identity value for mapping contigs
    """
    lowest_window_id = float('inf')
    expanded_cigar = get_expanded_cigar(cigar)

    for i in range(0, len(expanded_cigar) - window_size):
        cigar_window = expanded_cigar[i:i+window_size]
        window_id = cigar_window.count('=') / window_size
        if window_id < lowest_window_id:
            lowest_window_id = window_id
    if lowest_window_id == float('inf'):
        return 0.0
    return lowest_window_id


def get_alignment_stats(paf_filename, ref_name, ref_length, df_phred):
    """
    Function to process the mapping (*.paf) file for a given reference.
    :param paf_filename: tabular file with alignment information for an assembler
    :param ref_name: reference name to filter from the paf_filename
    :param ref_length: expected reference length
    :return:
        - contiguity: largest % of reference covered by a single contig
        - coverage:  % of the reference genome covered by the contigs (breadth of coverage)
        - lowest_identity: % of identity to the reference of the worst mapping contig
        - nID: Normalized identity by contig lenght
    """

    # Tracks the longest single alignment, in terms of the reference bases.
    covered_bases = []

    n_identity = []

    longest_alignment = 0

    aligment_dict = {'Reference': utils.REFERENCE_DIC[ref_name], 'Reference_Length': ref_length, 'Longest_Alignment': 0,
                     'Longest_Alignment_Cigar': '', 'Contigs': {}}

    with open(paf_filename) as paf:
        for line in paf:
            parts = line.strip().split('\t')
            if parts[5] == ref_name:
                # parse values from PAF file
                contig_name, contig_length = parts[0], int(parts[1])
                start, end = int(parts[7]), int(parts[8])

                # number of residue matches, alignment block length
                matching_bases, total_bases = int(parts[9]), int(parts[10])  # TODO
                cigar = parts[-1]

                if contig_name not in aligment_dict['Contigs'].keys():
                    aligment_dict['Contigs'][contig_name] = {'Length': contig_length, 'Base_Matches': matching_bases,
                                                             'Identity': None, 'Phred': None}
                else:
                    aligment_dict['Contigs'][contig_name]['Base_Matches'] += matching_bases

                if end - start > longest_alignment:
                    longest_alignment = end - start
                    longest_alignment_cigar = cigar
                longest_alignment = max(longest_alignment, end - start)
                covered_bases.append([start, end])

    # Calculate identity for all the contigs:
    for contig in aligment_dict['Contigs'].keys():
        aligment_dict['Contigs'][contig]['Identity'] = aligment_dict['Contigs'][contig]['Base_Matches'] / \
                                                       aligment_dict['Contigs'][contig]['Length']
        n_identity.append(aligment_dict['Contigs'][contig]['Base_Matches'])

        aligment_dict['Contigs'][contig]['Phred'] = get_phred_quality_score(aligment_dict['Contigs'][contig]['Identity'])
        df_phred = df_phred.append({'Assembler': os.path.basename(paf_filename).split('.')[0].rsplit('_')[-1],
                                    'Reference': aligment_dict['Reference'],
                                    'Contig': contig,
                                    'Contig Length': aligment_dict['Contigs'][contig]['Length'],
                                    'Phred Quality Score': aligment_dict['Contigs'][contig]['Phred']
                                    }, ignore_index=True)

    contiguity = longest_alignment / ref_length
    lowest_identity = get_lowest_window_identity(longest_alignment_cigar, 1000)

    coverage = get_covered_bases(covered_bases, ref_length)

    identity = sum(n_identity)/len(n_identity)

    return contiguity, coverage, lowest_identity, identity, df_phred


def parse_paf_files(df, mappings, print_csv=False):
    """
    Parses fasta, paf files references and returns info in dataframe.
    :param df: pandas DataFrame with assembly stats
    :param mappings: list of paf files
    :param print_csv: Bool to print csv with breadth of coverage values per reference for each assembler
    :return: pandas Dataframe with columns Reference, Assembler and C90
    """

    # Dataframe for C90 plot
    df_c90 = pd.DataFrame(columns=['Reference', 'Assembler', 'C90'])

    # Dataframe for Phred Score plot
    df_phred = pd.DataFrame(columns=['Assembler', 'Reference', 'Contig', 'Contig Length', 'Phred Quality Score'])

    for assembler in sorted(df['Assembler'].unique()):

        print('\n\n------' + assembler + '------\n')

        # filter dataframe for the assembler
        df_assembler = df[df['Assembler'] == assembler]

        # iterator for reference files (sequence length is needed)
        references = (x[1] for x in groupby(open(REFERENCE_SEQUENCES, "r"), lambda line: line[0] == ">"))

        paf_file = fnmatch.filter(mappings, '*_' + assembler + '.*')[0]

        print(','.join(["Reference", "Reference Length", "Contiguity", "Identity", "Lowest Identity",
                        "Breadth of Coverage", "C90", "C95", "Aligned Contigs", "NA50", "Aligned Bp"]))

        if print_csv:
            fh = open(assembler + "_breadth_of_coverage_contigs.csv", "w")
            fh.write("Reference, Breadth of Coverage, Contigs\n")

        for header in references:
            header_str = header.__next__()[1:].strip().split()[0]
            reference_name = utils.REFERENCE_DIC[header_str]
            seq = "".join(s.strip() for s in references.__next__())

            df_assembler_reference = df_assembler[df_assembler['Mapped'] == header_str]

            mapped_contigs = df_assembler_reference['Contig Len'].astype('int').tolist()

            na50 = utils.get_N50(mapped_contigs)
            c90 = get_c90(mapped_contigs, len(seq)/3)  # adjust for triple reference
            df_c90 = df_c90.append({'Reference': reference_name, 'Assembler': assembler, 'C90': c90}, ignore_index=True)
            c95 = get_c95(mapped_contigs, len(seq)/3)  # adjust for triple reference

            contiguity, coverage, lowest_identity, identity, df_phred = get_alignment_stats(paf_file,
                                                                                            header_str,
                                                                                            len(seq)/3,
                                                                                            df_phred)

            if print_csv:
                fh.write(','.join([reference_name, str(coverage), str(len(mapped_contigs))]) + '\n')

            print(','.join([reference_name, f'{len(seq)/3}', f'{contiguity:.2f}', f'{identity:.6f}',
                            f'{lowest_identity:.6f}', f'{coverage:.2f}', f'{c90}', f'{c95}',
                            f'{len(mapped_contigs)}', f'{na50}', f'{sum(mapped_contigs)}']))

        if print_csv:
            fh.close()

    return df_c90, df_phred


def add_matching_ref(df, mappings):
    """
    For each contig in the df, adds the correspondent reference if the contig is mapped. Drops the unmapped contigs.
    :param df: Pandas Dataframe with stats for each contig
    :param mappings: list of paf files
    :return: Pandas Dataframe with stats for each contig with reference info instead of 'Mapped' and rows with
    unmapped contigs removed
    """
    for assembler in sorted(df['Assembler'].unique()):
        paf_file = fnmatch.filter(mappings, '*_' + assembler + '.*')[0]
        mapped_contigs = utils.get_mapped_contigs_with_ref(paf_file)  # dictionary with contigs
        
        for contig in df['Contig'][(df['Mapped'] == 'Mapped') & (df['Assembler'] == assembler)]:
            # get index.
            row_index = df[(df['Contig'] == contig) & (df['Mapped'] == 'Mapped') & (df['Assembler'] == assembler)]\
                .index.item()
            df.loc[row_index, 'Mapped'] = mapped_contigs[contig]  # update with reference

    # remove unmapped contigs from dataframe
    df = df.drop(df[df.Mapped == 'Unmapped'].index)
    return df


def main():
    try:
        assemblies = glob.glob(sys.argv[1] + '/*.fasta')
        mappings = glob.glob(sys.argv[2] + '/*.paf')

    except IndexError as e:
        print(e, "files not found")
        sys.exit(0)

    try:
        if sys.argv[3] == "--print-csv":
            print_csv = True
    except IndexError as e:
        print_csv = False

    # Dataframe with assembly info
    df = utils.parse_assemblies(assemblies, mappings)

    # Add correspondent reference to each dataframe contig
    df = add_matching_ref(df, mappings)

    # Get and print mapping stats tables for each assembler
    to_plot_c90, to_plot_phred = parse_paf_files(df, mappings, print_csv)

    # Create plot - C90 per reference
    fig_c90 = go.Figure()
    i = 0
    for assembler in sorted(to_plot_c90['Assembler'].unique()):
        fig_c90.add_trace(go.Scatter(x=to_plot_c90['C90'][to_plot_c90['Assembler'] == assembler],
                                     y=to_plot_c90['Reference'][to_plot_c90['Assembler'] == assembler],
                                     mode='markers', name=assembler, opacity=0.7,
                                     marker=dict(color=colours[i], size=24, line=dict(width=1, color='black'))))
        i += 1
    fig_c90.update_layout(title="C90 per reference genome for each assembler",
                          xaxis_title="Contigs",
                          xaxis_type="log",
                          plot_bgcolor='rgb(255,255,255)',
                          xaxis=dict(showline=True, zeroline=False, linewidth=1, linecolor='black', gridcolor='#DCDCDC')
                          )

    plot(fig_c90, filename='c90.html')

    # Create plot - Phred Score per contig, per reference
    fig_phred = go.Figure()

    num_cols = 2
    num_rows = int(len(to_plot_phred['Reference'].unique()) / num_cols)

    # define number and organization of subplots
    phred_subplots = subplots.make_subplots(rows=num_rows, cols=num_cols,
                                            shared_yaxes=True, shared_xaxes=True,
                                            subplot_titles=to_plot_phred['Reference'].unique(),
                                            horizontal_spacing=0.04,
                                            vertical_spacing=0.08)
    r, c = 1, 1

    for reference in sorted(to_plot_phred['Reference'].unique()):
        tracers = []
        legend = True if r == 1 and c == 1 else False
        i = 0
        for assembler in to_plot_phred['Assembler'].unique():
            tracer = go.Scatter(y=to_plot_phred['Phred Quality Score'][(to_plot_phred['Reference'] == reference) &
                                                                       (to_plot_phred['Assembler'] == assembler)],
                                x=to_plot_phred['Contig Length'][(to_plot_phred['Reference'] == reference) &
                                                                 (to_plot_phred['Assembler'] == assembler)],
                                name=assembler,
                                legendgroup='group{}'.format(i),
                                showlegend=legend,
                                opacity=0.7,
                                mode='markers',
                                marker=dict(color=colours[i], size=12, line=dict(width=1, color='black'))
                                )
            i += 1
            tracers.append(tracer)

        for t in tracers:
            phred_subplots.add_trace(t, r, c)

        # define the next subplot that will be populated with tracer data
        c += 1
        if c > num_cols:
            r += 1
            c = 1
    # phred_subplots.update_xaxes(type="log") TODO

    plot(phred_subplots, filename='phred_scatter.html', auto_open=True)


if __name__ == '__main__':
    main()
