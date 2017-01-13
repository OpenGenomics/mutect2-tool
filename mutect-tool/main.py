#!/usr/bin/env python

import argparse
import logging
import os
import sys
from cdis_pipe_utils import pipe_util
from cdis_pipe_utils import postgres

import tools.mutect_tool as mutect_tool


def is_nat(x):
    '''
    Checks that a value is a natural number.
    '''
    if int(x) > 0:
        return int(x)
    raise argparse.ArgumentTypeError('%s must be positive, non-zero' % x)

def main():
    parser = argparse.ArgumentParser('GATK MuTect2 Variant Calling Pipeline')

    # Logging flags.
    parser.add_argument('-d', '--debug',
        action = 'store_const',
        const = logging.DEBUG,
        dest = 'level',
        help = 'Enable debug logging.',
    )
    parser.set_defaults(level = logging.INFO)

    # Required flags.

    parser.add_argument('-r', '--reference_fasta_path',
                        required = False,
                        help = 'Reference fasta path.',
    )

    parser.add_argument('-rf', '--reference_fasta_fai',
                        required = False,
                        help = 'Reference fasta fai path.',
    )

    parser.add_argument('-dbsnp', '--known_snp_vcf_path',
                        required = False,
                        help='Reference SNP path.',
    )

    parser.add_argument('-cosmic', '--cosmic_path',
                        required = False,
                        help='Reference COSMIC path.',
    )
    parser.add_argument('-pon', '--pon_path',
                        required = False,
                        help='Reference Panel Of Normal path.',
    )

    parser.add_argument('-n', '--normal_bam_path',
                        required = False,
                        help = 'normal bam path.',
    )

    parser.add_argument('-t', '--tumor_bam_path',
                        required = False,
                        help = 'tumor bam path',
    )

    parser.add_argument('-j', '--thread_count',
                        required = False,
                        type = is_nat,
                        help = 'Maximum number of threads for execution.',
    )

    parser.add_argument('-jh', '--java_heap',
                        required = False,
                        help = 'Maximum number of java heap memory.',
    )

    parser.add_argument('-bs', '--Parallel_Block_Size',
                        type = is_nat,
                        default = 50000000,
                        required = False,
                        help = 'Parallel Block Size',
    )

    parser.add_argument('--contEst',
                        required = True,
                        help = 'Contamination estimation value from ContEst'
    )
    parser.add_argument("--dontUseSoftClippedBases",
                        help="If specified, it will not analyze soft clipped bases in the reads",
                        action="store_true")

    db = parser.add_argument_group("Database parameters")
    db.add_argument("--host", default='172.17.65.79', help='hostname for db')
    db.add_argument("--database", default='prod_bioinfo', help='name of the database')
    db.add_argument("--postgres_config", default=None, help="postgres config file", required=True)

    optional = parser.add_argument_group("optional input parameters")
    optional.add_argument("--normal_id", default="unknown", help="unique identifier for normal dataset")
    optional.add_argument("--tumor_id", default="unknown", help="unique identifier for normal dataset")
    optional.add_argument("--case_id", default="unknown", help="unique identifier")
    optional.add_argument("--outdir", default="./", help="path for logs etc.")

    args = parser.parse_args()
    case_id = args.case_id
    normal_id = args.normal_id
    tumor_id = args.tumor_id
    thread_count = str(args.thread_count)
    contEst = str(args.contEst)
    java_heap = str(args.java_heap)

    logger = pipe_util.setup_logging('gatk_mutect2', args, case_id)

    hostname = os.uname()[1]
    logger.info('hostname=%s' % hostname)

    s = open(args.postgres_config, 'r').read()
    postgres_config = eval(s)

    DATABASE = {
        'drivername': 'postgres',
        'host' : args.host,
        'port' : '5432',
        'username': postgres_config['username'],
        'password' : postgres_config['password'],
        'database' : args.database
    }


    engine = postgres.db_connect(DATABASE)
    mode = pipe_util.get_param(args, 'dontUseSoftClippedBases')
    normal_bam_path = pipe_util.get_param(args, 'normal_bam_path')
    tumor_bam_path = pipe_util.get_param(args, 'tumor_bam_path')
    reference_fasta_path = pipe_util.get_param(args, 'reference_fasta_path')
    fai_path = pipe_util.get_param(args, 'reference_fasta_fai')
    blocksize = pipe_util.get_param(args, 'Parallel_Block_Size')
    pon_path = pipe_util.get_param(args, 'pon_path')
    known_snp_vcf_path = pipe_util.get_param(args, 'known_snp_vcf_path')
    cosmic_path = pipe_util.get_param(args, 'cosmic_path')
    mutect_tool.run_mutect(case_id, normal_id, normal_bam_path, tumor_id, tumor_bam_path, known_snp_vcf_path, cosmic_path, thread_count, java_heap, reference_fasta_path, contEst, pon_path, fai_path, blocksize, engine, logger, mode)


if __name__ == '__main__':

    main()