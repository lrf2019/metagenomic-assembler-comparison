#!/usr/bin/env python3
"""
TODO - Add description
     - Improve this....
"""

import sys
from itertools import groupby
from plotly.offline import plot
import glob
import os
import fnmatch
import pandas as pd
import plotly.graph_objects as go



COLOURS = ['#003f5c', '#2f4b7c', '#665191', '#a05195', '#d45087', '#f95d6a', '#ff7c43', '#ffa600']
COLUMNS = ['Assembler','Contig', 'Contig Len', 'Mapped']


def fasta_iter(fasta_name):
    """
    modified from Brent Pedersen
    Correct Way To Parse A Fasta File In Python
    given a fasta file. yield tuples of header, sequence
    """
    fh = open(fasta_name)

    # ditch the boolean (x[0]) and just keep the header or sequence since
    # we know they alternate.
    faiter = (x[1] for x in groupby(fh, lambda line: line[0] == ">"))

    for header in faiter:
        # drop the ">"
        headerStr = header.__next__()[1:].strip().split()[0]

        # join all sequence lines to one.
        try:
            seq = "".join(s.strip() for s in faiter.__next__())
        except StopIteration:
            print(headerStr)

        yield (headerStr, seq)


def get_n50(contig_lengths):
    """

    :param contig_lengths:
    :return:
    """
    contig_lengths = sorted(contig_lengths, reverse=True)
    total_length = sum(contig_lengths)
    target_length = total_length * 0.5
    length_so_far = 0
    n50 = 0
    for contig_length in contig_lengths:
        length_so_far += contig_length
        if length_so_far >= target_length:
            n50 = contig_length
            break
    return n50

def get_mapped_contigs(paf_file):
    """
    Gets list with the sizes of the mapped contigs.
    In the paf file, the first col is the contig name,
    the second is the contig size (excludes gaps)
    :param paf_file: path to the PAF file
    :return: list with contig sizes
    """
    with open(paf_file) as f:
        mapped_contigs = [line.split()[0] for line in f]
    return mapped_contigs


def order_contigs(contig_list):
    """

    :param contig_list:
    :return:
    """

def main():
    try:
        assemblies = glob.glob(sys.argv[1] + '/*')
        mappings = glob.glob(sys.argv[2] + '/*')

    except IndexError as e:
        print(e, "files not found")
        sys.exit(0)

    df = pd.DataFrame(columns=COLUMNS)


    print(','.join(['Assembler', 'n Contigs', 'total bp', 'max contig size', 'n50', '% mapped contigs',
                    '% mapped bp']))

    for file in assemblies:

        filename = os.path.basename(file).split('.')[0].rsplit('_')[-1]
        mapped_contigs = get_mapped_contigs(fnmatch.filter(mappings, '*_'+filename+'.*')[0])


        fasta = fasta_iter(file)
        for header, seq in fasta:
            if header in mapped_contigs:
                is_mapped = 'Mapped'
            else:
                is_mapped = 'Unapped'

            df = df.append({'Assembler': filename, 'Contig': header, 'Contig Len': len(seq), 'Mapped': is_mapped},
                           ignore_index=True)

    df = df.reset_index()

    # Create plot
    fig = go.Figure()

    for assembler in sorted(df['Assembler'].unique()):

        n_contigs = len(df['Contig Len'][df['Assembler'] == assembler])
        total_bp = sum(df['Contig Len'][df['Assembler'] == assembler])
        max_contig_size = max(df['Contig Len'][df['Assembler'] == assembler])
        n50 = get_n50(df['Contig Len'][df['Assembler'] == assembler])
        mapped_contigs = len([(df['Mapped'] == 'Mapped') & (df['Assembler'] == assembler)])
        mapped_bp = sum([(df['Mapped'] == 'Mapped') & (df['Assembler'] == assembler)])

        print(','.join([assembler, f'{n_contigs}', f'{total_bp}', f'{max_contig_size}', f'{n50}',
                        f'{mapped_contigs} ({(mapped_contigs/n_contigs)*100:.2f}%)',
                        f'{mapped_bp} ({(mapped_bp/total_bp)*100:.2f}%)']))

        fig.add_trace(go.Box(x=df['Contig Len'][df['Assembler'] == assembler], name=assembler, boxpoints='outliers',
                             boxmean=True, fillcolor='#D3D3D3', line=dict(color='#000000')))
        fig.add_trace(go.Box(x=df['Contig Len'][(df['Mapped'] == 'Unapped') & (df['Assembler'] == assembler)],
                             name=assembler, boxpoints='all', pointpos=0, marker=dict(color='rgba(178,37,34,0.7)'),
                             line=dict(color='rgba(0,0,0,0)'), fillcolor='rgba(0,0,0,0)'))

    fig.update_layout(showlegend=False, xaxis_type="log", xaxis_title="Contig size (Log bp)",
                      title="Contig size distribution per assembler (contigs over 1000 bp)",
                      plot_bgcolor='rgb(255,255,255)', xaxis=dict(zeroline=False, gridcolor='#DCDCDC'))
    plot(fig)


if __name__ == '__main__':
    main()