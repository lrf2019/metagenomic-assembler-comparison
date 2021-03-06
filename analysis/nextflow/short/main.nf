#!/usr/bin/env nextflow

import Helper
import CollectInitialMetadata

// Pipeline version
if (workflow.commitId){
    version = "0.1 $workflow.revision"
} else {
    version = "0.1 (local version)"
}

params.help = false
if (params.help){
    Help.print_help(params)
    exit 0
}

def infoMap = [:]
if (params.containsKey("fastq")){
    infoMap.put("fastq", file(params.fastq).size())
}

//Help.start_info(infoMap, "$workflow.start", "$workflow.profile", version)
CollectInitialMetadata.print_metadata(workflow)

// MAIN PARAMETERS
//      Fastq
if (params.fastq instanceof Boolean){exit 1, "'fastq' must be a path pattern. Provide value:'$params.fastq'"}
if (!params.fastq){ exit 1, "'fastq' parameter missing"}
// size: -1 -> allows for single and paired-end files to be passed through. Change if necessary
IN_fastq_raw = Channel.fromFilePairs(params.fastq, size: -1).ifEmpty { exit 1, "No fastq files provided with pattern:'${params.fastq}'" }

//      Clear
clear = params.clearInput ? "true" : "false"
checkpointClear = Channel.value(clear)


// SET CHANNELS FOR ASSEMBLERS
IN_fastq_raw.into{ IN_BCALM2; IN_GATB_MINIA; IN_MINIA; IN_MEGAHIT; IN_METASPADES; IN_UNICYCLER; IN_IDBA; IN_SPADES; IN_SKESA; IN_VELOUR; IN_VELVETOPTIMIZER; IN_PANDASEQ; IN_BBAP }


// BCALM 2

if ( !params.bcalmKmerSize.toString().isNumber() ){
    exit 1, "'bcalmKmerSize' parameter must be a number. Provided value: '${params.bcalmKmerSize}'"
}

process BCALM2 {

    tag {sample_id}
    publishDir "results/bcalm2/"

    input:
    set sample_id, file(fastq) from IN_BCALM2
    val KmerSize from Channel.value(params.bcalmKmerSize)

    output:
    set sample_id, file("*_BCALM2.fasta") into OUT_BCALM2

    script:
    """
    ls -1 $fastq  > list_reads
    bcalm -in list_reads -out ${sample_id} -kmer-size $KmerSize

    # workdir cleanup
    rm list_reads

    mv ${sample_id}.unitigs.fa  ${sample_id}_BCALM2.fasta
    """
}


// GATB MINIA
IN_GATB_kmers = Channel.value(params.gatbkmer)
IN_GATB_besst_iter = Channel.value(params.gatb_besst_iter)
GATB_error_correction = params.GATB_error_correction ? "true" : "false"
IN_error_correction = Channel.value(GATB_error_correction)

process GATBMINIAPIPELINE {

    tag {sample_id}
    publishDir 'results/GATBMiniaPipeline/'

    input:
    set sample_id, file(fastq_pair) from IN_GATB_MINIA
    val kmer_list from IN_GATB_kmers
    val do_error_correction from GATB_error_correction
    val besst_iter from IN_GATB_besst_iter

    output:
    set sample_id, file('*_GATBMiniaPipeline.fasta') into OUT_GATB

    script:
    """
    if [ $do_error_correction ];
    then
        gatb -1 ${fastq_pair[0]} -2 ${fastq_pair[1]} --kmer-sizes ${kmer_list} -o ${sample_id}_GATBMiniaPipeline
    else
        gatb -1 ${fastq_pair[0]} -2 ${fastq_pair[1]} --kmer-sizes ${kmer_list} -o ${sample_id}_GATBMiniaPipeline --no-error-correction
    fi

    link=\$(readlink ${sample_id}_GATBMiniaPipeline.fasta) && rm ${sample_id}_GATBMiniaPipeline.fasta && mv \$link ${sample_id}_GATBMiniaPipeline.fasta

    # rm temp dirs
    rm -r *_GATBMiniaPipeline.lib* *_GATBMiniaPipeline_besst *.unitigs* *contigs.fa *.h5
    rm *list_reads*

    """
}

// MINIA
IN_MINIA_kmer = Channel.value(params.miniakmer)
process MINIA {

    tag {sample_id}
    publishDir 'results/MINIA/'

    input:
    set sample_id, file(fastq) from IN_MINIA
    val kmer from IN_MINIA_kmer

    output:
    set sample_id, file('*_minia.fasta') into OUT_MINIA

    script:
    """
    ls -1 $fastq  > list_reads

    minia -in list_reads -out ${sample_id}_minia.fasta -nb-cores $task.cpu

    mv ${sample_id}_minia.fasta.contigs.fa ${sample_id}_minia.fasta

    rm list_reads *.unitigs.* *.h5
    """
}


// MEGAHIT

IN_megahit_kmers = Channel.value(params.megahitKmers)

process MEGAHIT {

    tag { sample_id }
    publishDir 'results/MEGAHIT/', pattern: '*_megahit*.fasta'

    input:
    set sample_id, file(fastq_pair) from IN_MEGAHIT
    val kmers from IN_megahit_kmers

    output:
    set sample_id, file('*_MEGAHIT.fasta') into OUT_MEGAHIT

    script:
    """
    /NGStools/megahit/bin/megahit --num-cpu-threads $task.cpus -o megahit --k-list $kmers -1 ${fastq_pair[0]} -2 ${fastq_pair[1]}
    mv megahit/final.contigs.fa ${sample_id}_MEGAHIT.fasta
    rm -r megahit
    """

}


// METASPADES

if ( params.metaspadesKmers.toString().split(" ").size() <= 1 ){
    if (params.metaspadesKmers.toString() != 'auto'){
        exit 1, "'metaspadesKmers' parameter must be a sequence of space separated numbers or 'auto'. Provided value: ${params.metaspadesKmers}"
    }
}
IN_metaspades_kmers = Channel.value(params.metaspadesKmers)

process METASPADES {

    tag { sample_id }
    publishDir 'results/MetaSPAdes/'

    input:
    set sample_id, file(fastq_pair) from IN_METASPADES
    val kmers from IN_metaspades_kmers

    output:
    set sample_id, file('*_metaspades.fasta') into OUT_METASPADES
    file('*_metaspades.fastg')

    script:
    """
    metaspades.py --only-assembler --threads $task.cpus -k $kmers -1 ${fastq_pair[0]} -2 ${fastq_pair[1]} -o metaspades
    mv metaspades/contigs.fasta ${sample_id}_metaspades.fasta
    mv metaspades/assembly_graph.fastg ${sample_id}_metaspades.fastg
    rm -r metaspades
    """
}


// UNICYCLER
process UNICYCLER {

    tag { sample_id }
    publishDir 'results/unicycler'

    input:
    set sample_id, file(fastq_pair) from IN_UNICYCLER

    output:
    set sample_id, file('*_unicycler.fasta') into OUT_UNICYCLER
    file('*_unicycler.gfa')

    script:
    """
    unicycler -t $task.cpus -o . --no_correct --no_pilon -1 ${fastq_pair[0]} -2 ${fastq_pair[1]}
    mv assembly.fasta ${sample_id}_unicycler.fasta
    mv assembly.gfa ${sample_id}_unicycler.gfa
    rm *best_spades_graph* *overlaps_removed* *bridges_applied* *final_clean*
    """
}


// SPADES
if ( params.spadesKmers.toString().split(" ").size() <= 1 ){
    if (params.spadesKmers.toString() != 'auto'){
        exit 1, "'spadesKmers' parameter must be a sequence of space separated numbers or 'auto'. Provided value: ${params.spadesKmers}"
    }
}
IN_spades_kmers = Channel.value(params.spadesKmers)

process SPADES {

    tag { sample_id }
    publishDir 'results/SPAdes/', pattern: '*.fasta'

    input:
    set sample_id, file(fastq_pair) from IN_SPADES
    val kmers from IN_spades_kmers

    output:
    set sample_id, file('*_spades.fasta') into OUT_SPADES
    file('*_spades.fastg')

    script:
    """
    spades.py --only-assembler --threads $task.cpus -k $kmers -1 ${fastq_pair[0]} -2 ${fastq_pair[1]} -o spades
    mv spades/contigs.fasta ${sample_id}_spades.fasta
    mv spades/assembly_graph.fastg ${sample_id}_spades.fastg
    rm -r spades
    """
}

// SKESA
process SKESA {

    tag { sample_id }
    publishDir 'results/skesa/'

    input:
    set sample_id, file(fastq_pair) from IN_SKESA

    output:
    set sample_id, file('*_skesa.fasta') into OUT_SKESA

    script:
    """
    skesa --cores $task.cpus --memory $task.memory --use_paired_ends --contigs_out ${sample_id}_skesa.fasta --fastq ${fastq_pair[0]} ${fastq_pair[1]}
    """
}


// PANDASEQ
process PANDASEQ {

    tag { sample_id }
    publishDir 'results/pandaseq'

    input:
    set sample_id, file(fastq_pair) from IN_PANDASEQ

    output:
    set sample_id, file('*pandaseq.fasta') into OUT_PANDASEQ

    script:
    """
    cp -r /NGStools/pandaseq pandaseq/

    ./pandaseq/pandaseq -T $task.cpus -w ${sample_id}_pandaseq.fasta -f ${fastq_pair[0]} -r ${fastq_pair[1]} -B
    rm -r pandaseq
    """
}


// VelvetOptimizerl
process VELVETOPTIMIZER {
    tag { sample_id }
    publishDir 'results/velvet_optimiser/', pattern: '*fasta'

    input:
    set sample_id, file(fastq_pair) from IN_VELVETOPTIMIZER

    output:
    set sample_id, file('*.fasta') into OUT_VELVETOPTIMIZER

    script:
    """
    VelvetOptimiser.pl -v -s $params.velvetoptimizer_hashs -e $params.velvetoptimizer_hashe -t $task.cpus \
    -f '-shortPaired -fastq.gz -separate ${fastq_pair[0]} ${fastq_pair[1]}'

    mv auto_data*/contigs.fa ${sample_id}_velvetoptimizer.fasta
    rm -r auto_data*
    """

}


// IDBA
process reformat_IDBA {
    tag { sample_id }

    input:
    set sample_id, file(fastq_pair) from IN_IDBA

    output:
    set sample_id, file('*.fasta') into REFORMAT_IDBA

    script:
    "reformat.sh in=${fastq_pair[0]} in2=${fastq_pair[1]} out=${sample_id}_reads.fasta"
}

process IDBA {

    tag { sample_id }
    publishDir 'results/idba/', pattern: '*fasta'

    input:
    set sample_id, file(fasta_reads_single) from  REFORMAT_IDBA

    output:
    set sample_id, file('*_IDBA-UD.fasta') into OUT_IDBA

    script:
    """
    idba_ud -l ${fasta_reads_single} --num_threads $task.cpus -o .
    mv contig.fa ${sample_id}_IDBA-UD.fasta
    rm begin align-* contig-* graph-* kmer local-*
    """
}


// FILTER_ASSEMBLY
TO_FILTER = Channel.create()
IN_FILTER = TO_FILTER.mix(OUT_BCALM2, OUT_GATB, OUT_MINIA, OUT_MEGAHIT, OUT_METASPADES, OUT_UNICYCLER, OUT_SPADES, OUT_SKESA, OUT_PANDASEQ, OUT_VELVETOPTIMIZER, OUT_IDBA)

IN_minLen = Channel.value(params.minLength)

process FILTER_ASSEMBLY {

    tag {sample_id}
    publishDir 'results/filtered/'

    input:
    set sample_id, file(assembly) from IN_FILTER
    val minLen from IN_minLen

    output:
    file('filtered_*')

    script:
    "reformat.sh in=${assembly} out=filtered_${assembly} minlength=${minLen}"
}
